from __future__ import annotations

import sys
from contextlib import contextmanager
from dataclasses import dataclass
from dataclasses import MISSING
from dataclasses import replace
from functools import wraps
from inspect import signature
from types import FunctionType
from types import NoneType
from typing import Any
from typing import Callable
from typing import cast
from typing import get_args
from typing import get_type_hints
from typing import TypeAlias
from typing import TypeVar

from flask import Flask
from flask import make_response
from flask import request
from flask import Response
from pydantic import BaseModel
from pydantic import create_model
from pydantic.error_wrappers import ValidationError
from werkzeug.datastructures import CombinedMultiDict
from werkzeug.datastructures import FileStorage
from werkzeug.datastructures import MultiDict

from .types import ErrorDict
from .types import Failure
from .types import Generic
from .types import ModelType
from .types import ModelTypeOrMissing
from .types import Success
from .typing import Literal
from .typing import TSBuilder
from .typing import TSField
from .typing import TSInterface
from .utils import FlaskValueError
from .utils import getdict
from .utils import is_literal
from .utils import jquery_form
from .utils import JsonDict
from .utils import lenient_issubclass
from .utils import maybeclose
from .utils import multidict_json
from .utils import tojson

# from .utils import unwrap

DecoratedCallable = TypeVar("DecoratedCallable", bound=Callable[..., Any])


Decoding: TypeAlias = Literal[None, "devalue", "jquery"]
ExcFunc: TypeAlias = Callable[[list[ErrorDict], bool], Response]


@dataclass
class Config:
    decoding: Decoding = None
    onexc: ExcFunc | None = None
    result: bool | None = None


def patch(e: ValidationError, json: JsonDict) -> JsonDict:
    """try and patch list validation errors"""

    def list_patch(locs):
        *path, attr = locs
        tgt = json
        for loc in path:
            tgt = tgt[loc]
        # turn into a list
        val = tgt[attr]
        if not isinstance(val, list):
            tgt[attr] = [val]

    errs = e.errors()
    if not all(err["type"] == "type_error.list" for err in errs):
        raise e

    for err in errs:
        loc = err["loc"]
        list_patch(loc)

    return json


def converter(
    model: type[ModelType],
    path: list[str] | None = None,
    hasdefault: bool = False,
) -> Callable[[JsonDict], ModelTypeOrMissing]:
    # we would really, *really* like to use this
    # - simpler - converter ... but mulitple <select>s
    # with only one option selected doesn't return a list
    # so this may fail with a pydantic type_error.list

    def convert(values: JsonDict) -> ModelTypeOrMissing:
        values = getdict(values, path)
        if not values and hasdefault:
            return MISSING
        try:
            return model(**values)
        except ValidationError as e:
            return model(**patch(e, values))

    return convert


def funcname(func: FunctionType) -> str:
    while hasattr(func, "__wrapped__"):
        func = func.__wrapped__

    return func.__name__


def make_pydantic(
    name: str,
    *,
    annotations: dict[str, Any],
    defaults: dict[str, Any],
) -> type[BaseModel]:
    """create a pydantic class"""
    # this seems to work fine
    # return type(
    #     name,
    #     (BaseModel,),
    #     dict(__annotations__=annotations, **defaults),
    # )
    d = defaults.copy()
    for k, typ in annotations.items():
        d[k] = (typ, ... if k not in defaults else defaults[k])

    return create_model(name, **d)


T = TypeVar("T")


class ApiError(ValueError, Generic[T]):
    """Create an Error similar to sveltekits error"""

    def __init__(self, status: int, payload: T):
        super().__init__()
        self.status = status
        self.payload: T = payload

    def toerror(self) -> Any:
        return self.payload

    def json(self, *, indent: None | int | str = 2) -> str:
        payload = dict(status=self.status, error=self.toerror())
        return tojson(payload, indent=indent)


class Api:
    builder = TSBuilder()

    def __init__(
        self,
        name: str,
        *,
        onexc: ExcFunc | None = None,
        decoding: Decoding = None,
        result: bool = True,
        function_types: bool = False,
    ):
        if "." in name:
            name = name.split(".")[-1].title()
        self.name = name
        self.dataclasses: set[type[BaseModel]] = set()
        self.funcs: list[TSField] = []

        self.min_py = 1
        self.config = Config(onexc=onexc, decoding=decoding, result=result)
        self.function_types = function_types

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

    @contextmanager
    def namespace(self, ns: dict[str, Any]):
        # used with:
        # with api.namespace(locals()) as api:
        #   ....
        #
        old = self.builder.ns
        self.builder.ns = ns
        yield self
        self.builder.ns = old

    def add(self, *classes: type[BaseModel]) -> None:
        """Add random pydantic class to `flask ts` output"""
        # for cls in classes:
        #     if not lenient_issubclass(cls, BaseModel):
        #         raise ValueError(f"{cls.__name__} is not a pydantic class")
        for cls in classes:
            self.add_rec(cls)

    def add_rec(self, cls: type[BaseModel]) -> None:
        if not lenient_issubclass(cls, BaseModel):
            raise ValueError(f"{cls.__name__} is not a pydantic class")
        self.dataclasses.add(cls)

    def get_type_hints(self, func: DecoratedCallable):
        return get_type_hints(func, localns=self.builder.ns, include_extras=False)

    def create_api(
        self,
        func: DecoratedCallable,
    ) -> tuple[bool, bool, dict[str, Callable[[JsonDict], Any]]]:
        # we just need a few access functions that
        # fetch into Flask ImmutableMultiDict object (e.g. request.values)
        # and to deal with simple non-pydantic types (e.g. list[int])
        hints = self.get_type_hints(func)

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

        def literal_string(
            allowed: set[str],
            name: str,
        ) -> Callable[[JsonDict], Any]:
            def ok(values: JsonDict) -> Any:
                if name not in values and name in defaults:
                    return MISSING
                ret = values.get(name)
                if ret not in allowed:
                    raise FlaskValueError(ValueError("illegal value"), loc=name)
                return ret

            return ok

        def cvt(name: str, typ: type[Any]) -> Callable[[JsonDict], Any]:
            nonlocal has_file_storage
            targs = get_args(typ)
            if targs:
                # check type is list,set,tuple....
                # assume  list[int], set[float] etc.
                if len(targs) > 1:
                    if is_literal(typ):
                        allowed = {str(v) for v in targs}
                        return literal_string(allowed, name)
                    # say: query:str|None = None
                    if len(targs) > 2 or targs[-1] is not NoneType:
                        raise TypeError(f"can't do multi arguments {name}[{typ}]")
                    typ = targs[0]
                    return lambda values: getvalue(values, name, typ)
                arg = targs[0]
                if arg is Ellipsis:
                    raise TypeError("... ellipsis not allowed for argument type")
                # e.g. arg == int so int(value) acts as converter
                if issubclass(arg, BaseModel):
                    self.add_rec(arg)
                    arg = converter(arg)

                elif arg == FileStorage:
                    has_file_storage = True
                    arg = lambda v: v  # pass-through

                return lambda values: getseqvalue(values, name, typ, arg)

            elif issubclass(typ, BaseModel):
                convert = converter(
                    typ,
                    path=[name] if embed else None,
                    hasdefault=name in defaults,
                )
                self.add_rec(typ)
                return convert
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
            self.add_rec(hints["return"])

        if self.function_types and not has_file_storage and len(args) > 1:
            # create a pydantic type from function arguments
            pydant = make_pydantic(
                self.typename(func),
                annotations=args,
                defaults=defaults,
            )

            self.add_rec(pydant)  # type: ignore

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
        f = ts.anonymous().field(ts.name)
        self.funcs.append(f)
        # unwrap(func).__typescript_api__ = f

        asjson, embed, cargs = self.create_api(func)

        names = tuple(cargs.keys())

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
                values = self.get_req_values(config, names)
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
            try:
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
            except ApiError as e:
                # ApiErrors turn into a sveltekit type="error"
                return self.make_response(
                    e.json(),
                    400,
                    {"Content-Type": "application/json"},
                )
            except FlaskValueError as e:
                return doexc(e)

        return api_func  # type: ignore

    def get_req_values(self, config: Config, names: tuple[str, ...]) -> JsonDict:
        # requires a request context
        decoding = self.config.decoding if config.decoding is None else config.decoding

        if request.is_json:
            json = request.json
            assert json is not None
            if json is None:
                raise ValueError("no data")
            if decoding == "devalue":
                from .devalue.parse import unflatten as str2json

                json = str2json(json)
            if not isinstance(json, dict) and len(names) == 1:
                # maybe we have say `def myapi(myid: list[str])`
                # make it a dict
                json = {names[0]: json}
            else:
                raise ValueError("expecting json object")
            # assert isinstance(json, dict), type(json)
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
            v = tojson(Failure(errors=e.errors()))
        return self.make_response(
            v,
            200 if result else 400,
            {"Content-Type": "application/json"},
        )

    def make_response(self, stuff: str, code: int, headers: dict[str, str]) -> Response:
        return make_response(stuff, code, headers)

    def to_ts(self, name: str | None = None, *, file=sys.stdout) -> None:
        self.show_dataclasses(list(self.dataclasses), file=file)
        self.show_interface(name, file=file)

    def show_interface(self, name: str | None = None, *, file=sys.stdout) -> None:
        interface = TSInterface(name=name or self.name, fields=self.funcs)
        print(interface, file=file)

    @classmethod
    def show_dataclasses(
        cls,
        dataclasses: list[type[BaseModel]],
        file=sys.stdout,
    ) -> None:
        for model in dataclasses:
            print(cls.builder(model), file=file)
        for build_func in cls.builder.process_seen():
            print(build_func(), file=file)

    # @classmethod
    # def show_form_data(
    #     cls,
    #     dataclasses: list[type[BaseModel]],
    #     file=sys.stdout,
    # ) -> None:
    #     for model in dataclasses:
    #         print(f"// form data for {model.__name__}", file=file)
    #         print(cls.builder.to_form(model), file=file)

    def init_app(self, app: Flask) -> None:
        if "flask-typescript" not in app.extensions:
            app.extensions["flask-typescript"] = set()
            from .cli import init_cli

            init_cli(app)

        d = app.extensions["flask-typescript"]
        d.add(self)

    @classmethod
    def _get_dataclasses(
        cls,
        app: Flask,
        nosort: bool = False,
    ) -> tuple[list[type[BaseModel]], list[Api]]:
        d: list[Api] = list(app.extensions["flask-typescript"])
        dataclasses: set[type[BaseModel]] = set()
        for api in d:
            dataclasses |= api.dataclasses
        if not nosort:
            dc = sorted(dataclasses, key=lambda x: x.__name__)
            d = sorted(d, key=lambda x: x.name)
        else:
            dc = list(dataclasses)
        return dc, d

    @classmethod
    def generate_api(
        cls,
        app: Flask,
        out: str | None = None,
        without_interface: bool = False,
        nosort: bool = False,
    ):
        """Generate Typescript types for this Flask app."""
        if "flask-typescript" not in app.extensions:
            return
        dc, d = cls._get_dataclasses(app, nosort)

        with maybeclose(out, "wt") as fp:
            from .utils import get_preamble

            print("// generated by flask-typescript", file=fp)
            print(get_preamble(), file=fp)
            cls.show_dataclasses(dataclasses=dc, file=fp)
            if not without_interface:
                for api in d:
                    api.show_interface(api.name, file=fp)

    # @classmethod
    # def generate_form_data(
    #     cls,
    #     app: Flask,
    #     out: str | None = None,
    #     nosort: bool = False,
    # ):
    #     """Generate Typescript formdata for this Flask app."""
    #     if "flask-typescript" not in app.extensions:
    #         return
    #     dc, _ = cls._get_dataclasses(app, nosort)

    #     with maybeclose(out) as fp:
    #         print("// generated by flask-typescript", file=fp)

    #         cls.show_form_data(dataclasses=dc, file=fp)
