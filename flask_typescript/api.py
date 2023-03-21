from __future__ import annotations

import json
import sys
from dataclasses import MISSING
from dataclasses import replace
from functools import wraps
from inspect import signature
from types import FunctionType
from typing import Any
from typing import Callable
from typing import get_type_hints
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
from werkzeug.datastructures import ImmutableMultiDict

from .typing import INDENT
from .typing import NL
from .typing import TSBuilder
from .typing import TSField
from .typing import TSInterface
from .utils import flatten
from .utils import jquery_form
from .utils import lenient_issubclass
from .utils import maybe_close

DecoratedCallable = TypeVar("DecoratedCallable", bound=Callable[..., Any])


class FlaskValueError(ValueError):
    def __init__(self, exc: ValueError, loc: str, errtype: str = "unknown"):
        super().__init__()
        self.exc = exc
        self.loc = loc
        self.errtype = errtype

    def json(self, *, indent: None | int | str = 2) -> str:
        return json.dumps(self.errors(), indent=indent, default=pydantic_encoder)

    def errors(self):
        return [
            dict(
                loc=(self.loc,),
                msg=str(self.exc),
                type=f"value_error.{self.errtype}",
            ),
        ]


ExcFunc = TypeVar(
    "ExcFunc",
    bound=Callable[[ValidationError | FlaskValueError], Response],
)


def converter(
    model: type[BaseModel],
    prefix: list[str] | None = None,
) -> Callable[[ImmutableMultiDict], BaseModel]:
    cvt = convert_from_schema(model.schema(), prefix or [])

    def convert(values: ImmutableMultiDict) -> BaseModel:
        return model(**cvt(values))

    return convert


def convert_from_schema(
    schema: dict[str, Any],
    prefix: list[str],
) -> Callable[[ImmutableMultiDict], dict[str, Any]]:
    def dotted_toname(name: str) -> str:
        return ".".join(prefix + [name])

    # def php_toname(name:str) -> str:
    #     if not prefix:
    #         return name
    #     return prefix[0] + ''.join(f'[{s}]' for s in prefix[1:] + [name])

    toname = dotted_toname

    def mkgetlist(name: str, hasdefault: bool):
        name = toname(name)

        def getlist(values: ImmutableMultiDict):
            if hasdefault and name not in values:
                return MISSING
            return values.getlist(name)

        return getlist

    def mkgetval(name: str, hasdefault: bool):
        name = toname(name)

        def getval(values: ImmutableMultiDict):
            return values.get(name, MISSING)

        return getval

    def mkconvert(d: Callable[[ImmutableMultiDict], dict[str, Any]]):
        def convert(values: ImmutableMultiDict) -> dict[str, Any]:
            return d(values)

        return convert

    required = set(schema.get("required", []))
    ret = {}

    for name, p in schema["properties"].items():
        hasdefault = name not in required
        if "$ref" in p:
            loc, n = getname(p["$ref"])
            schema2 = schema[loc][n]
            d = convert_from_schema(schema2, prefix=prefix + [name])
            ret[name] = mkconvert(d)
            continue

        typ = p["type"]
        if typ == "array":
            ret[name] = mkgetlist(name, hasdefault)
        else:
            ret[name] = mkgetval(name, hasdefault)

    def convert(values: ImmutableMultiDict) -> dict[str, Any]:
        args = {}
        for name, cvt in ret.items():
            v = cvt(values)
            if v is MISSING:
                continue
            args[name] = v
        return args

    return convert


def repr(v):
    return json.dumps(v)


def getname(s: str) -> tuple[str, str]:
    "#/definitions/name"
    l, n = s.split("/")[-2:]
    return (l, n)


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
            if "$ref" in p:
                _, typ = getname(p["$ref"])
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
                v = repr(p["default"])
                default = f" /* ={v} */"
            else:
                q = ""
                default = ""
            row = f"{name}{q}: {typ}{default};"
            ret.append(row)
        return ret

    out = []
    definitions = schema.get("definitions")

    if definitions:
        for k, d in definitions.items():
            if k in seen:
                continue
            s = to_ts_schema(d, seen)
            out.append(s)
            seen.add(k)

    ret = props(schema["properties"])
    attrs = INDENT + (NL + INDENT).join(ret)

    s = f"""export type {schema['title']} = {{
{attrs}
}}"""
    out.append(s)
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
        onexc: Callable[[ValidationError | FlaskValueError], Response] | None = None,
        from_jquery: bool = False,
        as_devalue: bool = False,
    ):
        if "." in name:
            name = name.split(".")[-1].title()
        self.name = name
        self.dataclasses: set[type[BaseModel]] = set()
        self.funcs: list[TSField] = []
        self._onexc = onexc
        self.from_jquery = from_jquery
        self.as_devalue = as_devalue
        self.min_py = 1

    def __call__(
        self,
        func: DecoratedCallable | None = None,
        *,
        onexc: ExcFunc | None = None,
        as_devalue: bool | None = None,
        from_jquery: bool | None = None,
    ):
        if func is None:
            return lambda func: self.api(
                func,
                onexc=onexc,
                as_devalue=as_devalue,
                from_jquery=from_jquery,
            )
        return self.api(
            func,
            onexc=onexc,
            as_devalue=as_devalue,
            from_jquery=from_jquery,
        )

    def add(self, cls: type[BaseModel]) -> None:
        """Add random pydantic class to `flask ts` output"""
        if not lenient_issubclass(cls, BaseModel):
            raise ValueError(f"{cls.__name__} is not a pydantic class")
        self.dataclasses.add(cls)

    def create_api(
        self,
        func: DecoratedCallable,
    ) -> tuple[bool, dict[str, Callable[[ImmutableMultiDict], Any]]]:
        hints = get_type_hints(func, include_extras=True)

        defaults = {
            k: v.default
            for k, v in signature(func).parameters.items()
            if v.default is not v.empty
        }
        cargs = {}
        has_file_storage = False

        def getvalue(values: ImmutableMultiDict, name: str, t: type[Any]) -> Any:
            return t(values.get(name)) if name in values else MISSING

        def getseqvalue(
            values: ImmutableMultiDict,
            name: str,
            t: type[Any],
            arg: type[Any],
        ) -> Any:
            if name not in values and name in defaults:
                return MISSING
            ret = values.getlist(name)
            # catch ValueError?
            return t(arg(v) for v in ret)

        def cvt(name: str, typ: type[Any]) -> Callable[[ImmutableMultiDict], Any]:
            nonlocal has_file_storage
            if hasattr(typ, "__args__"):
                # check type is list,set,tuple....
                # assume  list[int], set[float] etc.
                if len(typ.__args__) > 1:
                    raise ValueError(f"can't do multi arguments {name}[{typ}]")
                arg = typ.__args__[0]
                if arg is Ellipsis:
                    raise ValueError("... ellipsis not allowed for argument type")
                # e.g. arg == int so int(value) acts as converter
                if issubclass(arg, BaseModel):
                    self.dataclasses.add(arg)
                    arg = converter(arg)

                elif arg == FileStorage:
                    has_file_storage = True
                    arg = lambda v: v  # pass-through

                return lambda values: getseqvalue(values, name, typ, arg)

            elif issubclass(typ, BaseModel):
                convert = converter(typ, prefix=[name] if embed else None)
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

        asjson = "return" in hints and issubclass(hints["return"], BaseModel)
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

        return asjson, cargs

    def typename(self, func) -> str:
        return f"Func{funcname(func).title()}"

    def api(
        self,
        func: DecoratedCallable,
        *,
        onexc: ExcFunc | None = None,
        as_devalue: bool | None = None,
        from_jquery: bool | None = None,
    ) -> DecoratedCallable:
        ts = self.builder(func)
        ts = replace(ts, isasync=True)
        self.funcs.append(TSField(name=ts.name, type=ts.anonymous()))

        asjson, cargs = self.create_api(func)

        def doexc(e):
            if onexc is not None:
                return onexc(e)
            if self._onexc is not None:
                return self._onexc(e)
            return self.onexc(e)

        @wraps(func)
        def api_func(*_args, **kwargs):
            args = {}
            name = None
            # this is probably async...
            values = self.get_req_values(as_devalue=as_devalue, from_jquery=from_jquery)
            try:
                for name, cvt in cargs.items():
                    v = cvt(values)
                    if v is not MISSING:
                        args[name] = v

            except ValidationError as e:
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
                ret = make_response(
                    ret.json(),
                    200,
                    {"Content-Type": "application/json"},
                )

            return ret

        return api_func  # type: ignore

    # def cache_get_req_values(self) -> ImmutableMultiDict:
    #     ret: ImmutableMultiDict
    #     if hasattr(g, "_flask_typescript"):
    #         return g._flask_typescript
    #     g._flask_typescript = ret = self.get_req_values()
    #     return ret

    def get_req_values(
        self,
        as_devalue: bool | None = None,
        from_jquery: bool | None = None,
    ) -> ImmutableMultiDict:
        if request.is_json:
            as_devalue = self.as_devalue if as_devalue is None else as_devalue
            json = request.json
            assert json is not None
            if as_devalue:
                from .devalue.parse import unflatten

                json = unflatten(json)

            return ImmutableMultiDict(
                dict(flatten(json)),
            )

        ret = CombinedMultiDict([request.args, request.form, request.files])  # type: ignore
        from_jquery = self.from_jquery if from_jquery is None else from_jquery
        if from_jquery:
            ret = jquery_form(ret)  # type: ignore
        return ret  # type: ignore

    def onexc(self, e: ValidationError | FlaskValueError) -> Response:
        return make_response(e.json(), 400, {"Content-Type": "application/json"})

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
        # seen: set[str] = set()
        for model in dataclasses:
            # print(to_ts(model, seen), file=file)
            print(cls.builder(model), file=file)

    def show_api(self, app: Flask, file=sys.stdout) -> None:
        self.to_ts(self.name or app.name.split(".")[-1].title(), file=file)

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
            def show_api(out: str | None = None, without_interface: bool = False):
                """Generate Typescript types for this Flask app."""
                d: set[Api] = app.extensions["flask-typescript"]
                dataclasses = set()
                for api in d:
                    dataclasses |= api.dataclasses
                with maybe_close(out) as fp:
                    Api.show_dataclasses(dataclasses=dataclasses, file=fp)
                    if not without_interface:
                        for api in d:
                            api.show_interface(api.name, file=fp)

        d = app.extensions["flask-typescript"]
        d.add(self)
