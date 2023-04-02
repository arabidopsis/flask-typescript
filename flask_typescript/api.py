from __future__ import annotations

import sys
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
from werkzeug.datastructures import CombinedMultiDict
from werkzeug.datastructures import FileStorage
from werkzeug.datastructures import MultiDict

from .types import Error
from .types import ErrorDict
from .types import ModelType
from .types import ModelTypeOrMissing
from .types import Success
from .typing import Literal
from .typing import TSBuilder
from .typing import TSField
from .typing import TSInterface
from .utils import dedottify
from .utils import FlaskValueError
from .utils import getdict
from .utils import jquery_form
from .utils import JsonDict
from .utils import lenient_issubclass
from .utils import maybe_close
from .utils import multidict_json
from .utils import tojson
from .utils import unflatten

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
        hints = get_type_hints(func, localns=self.builder.ns, include_extras=False)

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
                    path=[name] if embed else None,
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
        # json are just pure dictionaries....
        return not isinstance(self.data, MultiDict)
