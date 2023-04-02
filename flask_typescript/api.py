from __future__ import annotations

import json
import re
import sys
from dataclasses import _MISSING_TYPE
from dataclasses import dataclass
from dataclasses import MISSING
from dataclasses import replace
from functools import wraps
from inspect import signature
from types import FunctionType
from typing import Any
from typing import Callable
from typing import cast
from typing import get_type_hints
from typing import TypeAlias
from typing import TypeGuard
from typing import TypeVar

import click
from flask import Flask
from flask import make_response
from flask import request
from flask import Response
from pydantic import BaseModel
from pydantic.error_wrappers import ValidationError
from pydantic.json import pydantic_encoder
from werkzeug.datastructures import CombinedMultiDict
from werkzeug.datastructures import FileStorage
from werkzeug.datastructures import MultiDict

from .types import Error
from .types import ErrorDict
from .types import Success
from .typing import INDENT
from .typing import Literal
from .typing import NL
from .typing import TSBuilder
from .typing import TSField
from .typing import TSInterface
from .utils import dedottify
from .utils import jquery_form
from .utils import JsonDict
from .utils import lenient_issubclass
from .utils import maybe_close
from .utils import multidict_json
from .utils import unflatten

DecoratedCallable = TypeVar("DecoratedCallable", bound=Callable[..., Any])


MaybeDict: TypeAlias = dict[str, Any] | None
MissingDict: TypeAlias = dict[str, Any] | _MISSING_TYPE
MaybeModel: TypeAlias = BaseModel | _MISSING_TYPE

Decoding: TypeAlias = Literal[None, "devalue", "jquery"]
ExcFunc: TypeAlias = Callable[[list[ErrorDict], bool], Response]
# ExcFunc = TypeVar(
#     "ExcFunc",
#     bound=Callable[[list[ErrorDict],bool], Response],
# )


def tojson(v: Any, indent: None | int | str = 2) -> str:
    return json.dumps(v, indent=indent, default=pydantic_encoder)


@dataclass
class Config:
    decoding: Decoding = None
    onexc: ExcFunc | None = None
    result: bool | None = None


CamelCase = re.compile(r"(?<!^)(?=[A-Z])")


class FlaskValueError(ValueError):
    """Create an Error similar to pydantic's ValidationError"""

    def __init__(self, exc: ValueError, loc: str, errtype: str = "malformed"):
        super().__init__()
        self.exc = exc
        self.loc = loc
        self.errtype = errtype

    @property
    def exc_name(self) -> str:
        return CamelCase.sub("_", self.exc.__class__.__name__).lower()

    def json(self, *, indent: None | int | str = 2) -> str:
        return tojson(self.errors(), indent=indent)

    def errors(self) -> list[ErrorDict]:
        return [
            dict(
                loc=(self.loc,),
                msg=str(self.exc),
                type=f"{self.exc_name}.{self.errtype}",
            ),
        ]


def getdict(values: JsonDict, prefix: list[str] | None = None) -> JsonDict:
    if prefix is None:
        return values
    for attr in prefix:
        if attr in values:
            values = values[attr]
            if not isinstance(values, dict):
                raise ValueError(f"{'.'.join(prefix)}: bad path")
        else:
            return {}
    return values


def pyconverter(
    model: type[BaseModel],
    prefix: list[str] | None = None,
    hasdefault: bool = False,
) -> Callable[[JsonDict], MaybeModel]:
    # we would really, *really* like to use this
    # - simpler - converter ... but mulitple <select>s
    # with only one option selected doesn't return a list
    # so this may fail with a pydantic type_error.list

    def convert(values: JsonDict) -> MaybeModel:
        values = getdict(values, prefix)
        if not values and hasdefault:
            return MISSING

        return model(**values)

    return convert


ModelType = TypeVar("ModelType", bound=BaseModel)


def converter(
    model: type[ModelType],
    *,
    prefix: list[str] | None = None,
    hasdefault: bool = False,
) -> Callable[[JsonDict], ModelType | _MISSING_TYPE]:
    """Complex converter necessitated by select problems (see note above)"""
    ret = convert_from_schema(model.schema(), hasdefault=hasdefault)

    cvt = Converter(model.__name__, ret, hasdefault=hasdefault)

    def convert(values: JsonDict) -> ModelType | _MISSING_TYPE:
        values = getdict(values, prefix)
        args = cvt.convert(values)
        if args is None:
            return MISSING
        return model(**args)

    return convert


def convert_from_schema(
    schema: dict[str, Any],
    hasdefault: bool = False,
):
    return convert_from_schema_(
        schema,
        global_schema=schema,
        hasdefault=hasdefault,
        seen=dict(),
    )


def convert_from_schema_(  # noqa: C901
    schema: dict[str, Any],
    global_schema: dict[str, Any],
    hasdefault: bool,
    seen: dict[str, Converter],
) -> dict[str, Callable[[JsonDict], Any]]:
    def mkgetlist(name: str, typ: str, hasdefault: bool):
        def getlist(values: JsonDict):
            if name not in values:
                if hasdefault:
                    return MISSING
                return []
            v = values[name]
            # **** all this to just check this!!!! ****
            if not isinstance(v, list):
                v = [v]
            return v

        return getlist

    def mkgetval(name: str, typ: str, hasdefault: bool):
        def getval(values: JsonDict):
            return values.get(name, MISSING)

        return getval

    def aschema(
        loc: Locator,
        hasdefault: bool,
    ) -> Converter:
        assert seen is not None
        # if we are already being built then return Converter instance
        if loc.key in seen:
            return seen[loc.key]
        seen[loc.key] = cvt = Converter(loc.typname, attrs={}, hasdefault=hasdefault)
        schema2 = loc.getdef(global_schema)
        ret = convert_from_schema_(
            schema2,
            global_schema=global_schema,
            hasdefault=hasdefault,
            seen=seen,
        )

        cvt.attrs = ret  # patch attributes
        return cvt

    def subschemas(
        attrname: str,
        lst: list[Locator],
        hasdefault: bool,
    ) -> Callable[[JsonDict], MissingDict]:
        cvts = [aschema(locator, hasdefault) for locator in lst]

        def convert_anyOf(values: JsonDict) -> MissingDict:
            values = getdict(values, [attrname])
            if not values:
                return MISSING
            for cvt in cvts:
                a = cvt.convert(values)
                if a is not None:
                    return a
            return MISSING

        return convert_anyOf

    if "properties" not in schema:
        # recursive definition?
        locator = locate_schema(schema["$ref"])
        cvt = aschema(locator, hasdefault=hasdefault)
        return cvt.attrs

    required = set(schema.get("required", []))
    ret: dict[str, Callable[[JsonDict], Any]] = {}

    for name, p in schema["properties"].items():
        hasdefault2 = name not in required
        if "type" not in p:
            if "$ref" in p:
                locators = [locate_schema(p["$ref"])]
            elif "anyOf" in p:
                # this is X | Y or a Generic
                locators = [locate_schema(t["$ref"]) for t in p["anyOf"]]
            elif "oneOf" in p:
                # this is what?
                locators = [locate_schema(t["$ref"]) for t in p["oneOf"]]
            # elif 'allOf' in p:
            # non existent intersection type!
            # this is what should be a singleton
            # typ = [locate_schema(t['$ref']) for t in p['allOf']]
            else:
                raise TypeError(f"can't find type for {name}: {p}")
            ret[name] = subschemas(name, locators, hasdefault2)

        else:
            typ = p["type"]
            if typ == "array":
                ret[name] = mkgetlist(name, p["items"]["type"], hasdefault2)
            else:
                ret[name] = mkgetval(name, typ, hasdefault2)

    return ret


class Converter:
    def __init__(
        self,
        typename: str,
        attrs: dict[str, Callable[[JsonDict], Any]] = {},
        hasdefault: bool = False,
        prefix: list[str] | None = None,
    ):
        self.typename = typename
        self.attrs = attrs
        self.hasdefault = hasdefault
        self.prefix = prefix

    def convert(self, values: JsonDict) -> MaybeDict:
        values = getdict(values, self.prefix)
        args = {}
        for name, cvt in self.attrs.items():
            v = cvt(values)
            if v is MISSING:
                continue
            args[name] = v
        if not args and self.hasdefault:
            return None
        return args

    def __call__(self, values: JsonDict) -> MaybeDict:
        return self.convert(values)


@dataclass
class Locator:
    key: str
    path: list[str]

    @property
    def typname(self):
        return self.path[-1]

    def getdef(self, schema: dict[str, Any]) -> dict[str, Any]:
        for p in self.path:
            if p == "#":
                continue
            if p not in schema:
                raise TypeError(f"bad path {self.path}")
            schema = schema[p]
            if not isinstance(schema, dict):
                raise TypeError(f"bad path {self.path}")
        return schema


def locate_schema(s: str) -> Locator:
    "e.g.: #/definitions/Type"
    return Locator(key=s, path=s.split("/"))


def jsonrepr(v):
    return json.dumps(v)


def to_ts(model: type[BaseModel], seen: set[str] | None = None) -> str:
    if seen is None:
        seen = set()
    if model.__name__ in seen:
        return ""
    schema = model.schema()
    try:
        return to_ts_schema(schema, seen)
    finally:
        seen.add(model.__name__)


def to_ts_schema(schema: dict[str, Any], seen: set[str]) -> str:
    def props(definitions):
        ret = []

        def gettype(p):
            if "type" not in p:
                if "$ref" in p:
                    _, typ = locate_schema(p["$ref"])
                elif "allOf" in p:
                    typ = "[" + " , ".join(gettype(t["$ref"]) for t in p["allOf"]) + "]"
                elif "anyOf" in p:
                    typ = " | ".join(gettype(t["$ref"]) for t in p["anyOf"])
                else:
                    # oneOf
                    raise ValueError("can't find type!")
            else:
                typ = p["type"]
            if typ == "array":
                islist = "[]"
                typ = gettype(p["items"])
            else:
                islist = ""
            if typ in {"integer", "float"}:
                typ = "number"
            return f"{typ}{islist}"

        for name, p in definitions.items():
            typ = gettype(p)
            if "default" in p:
                q = "?"
                v = jsonrepr(p["default"])
                default = f" /* ={v} */"
            else:
                q = ""
                default = ""
            row = f"{name}{q}: {typ}{default};"
            ret.append(row)
        return ret

    out = set()
    definitions = schema.get("definitions")

    if definitions:
        for k, d in definitions.items():
            if k in seen:
                continue
            s = to_ts_schema(d, seen)
            out.add(s)
            seen.add(k)
    # might not have properties if we have a self-ref type:
    #
    # class LinkedList(BaseModel):
    #   val: int = 123
    #   next: LinkedList|None = None
    #
    # only {'$ref': '#/definitions/LinkedList', 'definitions': {...}}
    if "properties" in schema:
        ret = props(schema["properties"])

        attrs = INDENT + (NL + INDENT).join(ret)

        s = f"""export type {schema['title']} = {{
{attrs}
}}"""
        out.add(s)
    return "\n".join(out)


def funcname(func: FunctionType) -> str:
    while hasattr(func, "__wrapped__"):
        func = func.__wrapped__

    return func.__name__


class Api:
    builder = TSBuilder()

    def __init__(
        self,
        name: str,
        *,
        onexc: ExcFunc | None = None,
        decoding: Decoding = None,
        result: bool = False,
    ):
        if "." in name:
            name = name.split(".")[-1].title()
        self.name = name
        self.dataclasses: set[type[BaseModel]] = set()
        self.funcs: list[TSField] = []

        self.min_py = 1
        self.config = Config(onexc=onexc, decoding=decoding, result=result)

    def __call__(
        self,
        func: DecoratedCallable | None = None,
        *,
        onexc: ExcFunc | None = None,
        decoding: Decoding = None,
        result: bool | None = None,
    ):
        config = Config(onexc=onexc, decoding=decoding, result=result)
        if func is None:
            return lambda func: self.api(
                func,
                config,
            )
        return self.api(
            func,
            config,
        )

    def add(self, cls: type[BaseModel]) -> None:
        """Add random pydantic class to `flask ts` output"""
        if not lenient_issubclass(cls, BaseModel):
            raise ValueError(f"{cls.__name__} is not a pydantic class")
        self.dataclasses.add(cls)

    def create_api(
        self,
        func: DecoratedCallable,
    ) -> tuple[bool, bool, dict[str, Callable[[JsonDict], Any]]]:
        # we just need a few access functions that
        # fetch into Flask ImmutableMultiDict object (e.g. request.values)
        # and to deal with simple non-pydantic types (e.g. list[int])
        hints = get_type_hints(func, localns=self.builder.ns, include_extras=True)

        defaults = {
            k: v.default
            for k, v in signature(func).parameters.items()
            if v.default is not v.empty
        }
        cargs = {}
        has_file_storage = False

        def getvalue(values: JsonDict, name: str, t: type[Any]) -> Any:
            return t(values.get(name)) if name in values else MISSING

        def getseqvalue(
            values: JsonDict,
            name: str,
            t: type[Any],
            arg: type[Any],
        ) -> Any:
            # e.g. for list[int]
            if name not in values and name in defaults:
                return MISSING
            ret = values.get(name, [])
            if not isinstance(ret, list):
                ret = [ret]

            # catch ValueError?
            def nomissing(v):
                val = arg(v)
                if val is MISSING:
                    raise FlaskValueError(ValueError("missing array value"), loc=name)
                return val

            return t(nomissing(v) for v in ret)

        def cvt(name: str, typ: type[Any]) -> Callable[[JsonDict], Any]:
            nonlocal has_file_storage
            if hasattr(typ, "__args__"):
                # check type is list,set,tuple....
                # assume  list[int], set[float] etc.
                if len(typ.__args__) > 1:
                    raise TypeError(f"can't do multi arguments {name}[{typ}]")
                arg = typ.__args__[0]
                if arg is Ellipsis:
                    raise TypeError("... ellipsis not allowed for argument type")
                # e.g. arg == int so int(value) acts as converter
                if issubclass(arg, BaseModel):
                    self.dataclasses.add(arg)
                    arg = converter(arg)

                elif arg == FileStorage:
                    has_file_storage = True
                    arg = lambda v: v  # pass-through

                return lambda values: getseqvalue(values, name, typ, arg)

            elif issubclass(typ, BaseModel):
                convert = converter(
                    typ,
                    prefix=[name] if embed else None,
                    hasdefault=name in defaults,
                )
                self.dataclasses.add(typ)
                return lambda values: convert(values)
            else:
                if typ == FileStorage:
                    has_file_storage = True
                    typ = lambda v: v  # type: ignore
                return lambda values: getvalue(values, name, typ)

        args = {name: t for name, t in hints.items() if name != "return"}
        npy = sum(1 for _, t in args.items() if lenient_issubclass(t, BaseModel))

        embed = npy > self.min_py  # or request.is_json

        cargs = {name: cvt(name, t) for name, t in args.items()}

        asjson = "return" in hints and lenient_issubclass(hints["return"], BaseModel)
        # todo check for iterator[BaseModel] too...
        if asjson:
            self.dataclasses.add(hints["return"])

        if not has_file_storage and len(args) > 0:
            # create a pydantic type from function arguments
            pydant = type(
                self.typename(func),
                (BaseModel,),
                dict(__annotations__=args, **defaults),
            )
            self.dataclasses.add(pydant)  # type: ignore

        return asjson, embed, cargs

    def typename(self, func) -> str:
        return f"Func{funcname(func).title()}"

    @property
    def is_json(self):
        return request.is_json

    def api(
        self,
        func: DecoratedCallable,
        config: Config,
    ) -> DecoratedCallable:
        ts = self.builder(func)
        result = config.result if config.result is not None else self.config.result

        if result is True:
            ts = replace(ts, result=result)
        ts = replace(ts, isasync=True)
        self.funcs.append(ts.anonymous().field(ts.name))

        asjson, embed, cargs = self.create_api(func)

        def doexc(e: ValidationError | FlaskValueError) -> Response:
            onexc = config.onexc or self.config.onexc
            if onexc is not None:
                errs = cast(list[ErrorDict], e.errors())
                return onexc(errs, result or False)
            return self.onexc(e, result=result or False)

        @wraps(func)
        def api_func(*_args, **kwargs):
            args = {}
            name = None
            # this is probably async...
            try:
                values = self.get_req_values(config)
                for name, cvt in cargs.items():
                    v = cvt(values)
                    if v is not MISSING:
                        args[name] = v

            except ValidationError as e:
                if name and (self.is_json or embed):
                    for err in e.errors():
                        err["loc"] = (name,) + err["loc"]
                return doexc(e)

            except ValueError as e:
                return doexc(FlaskValueError(e, name))

            kwargs.update(args)
            ret = func(**kwargs)
            if asjson:
                if not isinstance(ret, BaseModel):
                    # this is a bug!
                    raise ValueError(
                        f"type signature for {funcname(func)} returns a pydantic instance, but we have {ret}",
                    )
                if result:
                    ret = Success(result=ret)
                ret = self.make_response(
                    ret.json(),
                    200,
                    {"Content-Type": "application/json"},
                )

            return ret

        return api_func  # type: ignore

    def get_req_values(
        self,
        config: Config,
    ) -> JsonDict:
        # requires a request context
        decoding = self.config.decoding if config.decoding is None else config.decoding

        if request.is_json:
            json = request.json
            assert json is not None
            if decoding == "devalue":
                from .devalue.parse import unflatten as str2json

                json = str2json(json)
            assert isinstance(json, dict), type(json)
            return json

        ret: MultiDict = CombinedMultiDict([request.args, request.form, request.files])

        if decoding == "jquery":
            json = jquery_form(ret)
        else:
            json = multidict_json(ret)

        return json

    def onexc(self, e: ValidationError | FlaskValueError, result: bool) -> Response:
        if not result:
            v = e.json()
        else:
            v = tojson(Error(error=e.errors()))
        return self.make_response(
            v,
            200 if result else 400,
            {"Content-Type": "application/json"},
        )

    def make_response(self, stuff: str, code: int, headers: dict[str, str]) -> Response:
        return make_response(stuff, code, headers)

    def to_ts(self, name: str | None = None, *, file=sys.stdout) -> None:
        self.show_dataclasses(self.dataclasses, file=file)
        self.show_interface(name, file=file)

    def show_interface(self, name: str | None = None, *, file=sys.stdout) -> None:
        interface = TSInterface(name=name or self.name, fields=self.funcs)
        print(interface, file=file)
        # for build_func in self.builder.process_seen():
        #     print(build_func())

    @classmethod
    def show_dataclasses(
        cls,
        dataclasses: set[type[BaseModel]],
        file=sys.stdout,
    ) -> None:
        for model in dataclasses:
            print(cls.builder(model), file=file)

    # def show_api(self, app: Flask, file=sys.stdout) -> None:
    #     self.to_ts(self.name or app.name.split(".")[-1].title(), file=file)

    def init_app(self, app: Flask) -> None:
        if "flask-typescript" not in app.extensions:
            app.extensions["flask-typescript"] = set()

            @app.cli.command("ts")
            @click.option(
                "-o",
                "--out",
                type=click.Path(dir_okay=False),
                help="output file",
            )
            @click.option(
                "-x",
                "--without-interface",
                is_flag=True,
                help="don't output interface(s)",
            )
            @click.option(
                "-s",
                "--sort",
                is_flag=True,
                help="sort output of pydantic classes by name",
            )
            def generate_api(
                out: str | None = None,
                without_interface: bool = False,
                sort: bool = False,
            ):
                """Generate Typescript types for this Flask app."""
                self.generate_api(app, out, without_interface, sort)

        d = app.extensions["flask-typescript"]
        d.add(self)

    def generate_api(
        self,
        app: Flask,
        out: str | None = None,
        without_interface: bool = False,
        sort: bool = False,
    ):
        """Generate Typescript types for this Flask app."""
        if "flask-typescript" not in app.extensions:
            return
        d: set[Api] = app.extensions["flask-typescript"]
        dataclasses = set()
        for api in d:
            dataclasses |= api.dataclasses
        if sort:
            dataclasses = set(sorted(dataclasses, key=lambda x: x.__name__))
            d = set(sorted(d, key=lambda x: x.name))
        with maybe_close(out) as fp:
            from .preamble import PREAMBLE

            print("// generated by flask-typescript", file=fp)
            print(PREAMBLE, file=fp)
            Api.show_dataclasses(dataclasses=dataclasses, file=fp)
            if not without_interface:
                for api in d:
                    api.show_interface(api.name, file=fp)


def multi(val) -> TypeGuard[MultiDict]:
    return isinstance(val, MultiDict)


class DebugApi(Api):
    """Version of Api that doesn't require a request context. Used for testing"""

    def __init__(
        self,
        name: str,
        data: MultiDict | dict[str, Any] | str,
        *,
        onexc: ExcFunc | None = None,
        decoding: Decoding = None,
        result: bool = False,
    ):
        super().__init__(
            name,
            onexc=onexc,
            decoding=decoding,
            result=result,
        )
        self.data = data

    def get_req_values(
        self,
        config: Config,
    ) -> JsonDict:
        decoding = self.config.decoding if config.decoding is None else config.decoding

        data = self.data

        if decoding == "jquery":
            if not multi(data):
                raise TypeError("not a MultiDict for from_jquery")
            data = jquery_form(data)
        elif decoding == "devalue":
            if multi(data):
                raise TypeError("not a json object for as_devalue")
            if isinstance(data, str):
                from .devalue.parse import parse

                data = parse(data)
        else:
            if multi(data):
                data = dedottify(unflatten(data))

        assert isinstance(data, dict)

        return data

    def make_response(self, stuff: str, code: int, headers: dict[str, str]) -> Response:
        return Response(stuff, code, headers)

    @property
    def is_json(self):
        return not isinstance(self.data, MultiDict)
