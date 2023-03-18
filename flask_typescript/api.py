from __future__ import annotations

import json
import sys
from dataclasses import MISSING
from dataclasses import replace
from functools import wraps
from inspect import signature
from typing import Any
from typing import Callable
from typing import get_type_hints
from typing import Iterator

import click
from flask import Flask
from flask import g
from flask import make_response
from flask import request
from flask import Response
from pydantic import BaseModel
from pydantic import ValidationError
from werkzeug.datastructures import CombinedMultiDict
from werkzeug.datastructures import FileStorage
from werkzeug.datastructures import ImmutableMultiDict

from .typing import INDENT
from .typing import NL
from .typing import TSBuilder
from .typing import TSField
from .typing import TSInterface


def converter(
    model: type[BaseModel],
    prefix: str = "",
) -> Callable[[ImmutableMultiDict], BaseModel]:
    cvt = convert_from_schema(model.schema(), prefix)

    def convert(values: ImmutableMultiDict) -> BaseModel:
        return model(**cvt(values))

    return convert


def convert_from_schema(
    schema: dict[str, Any],
    prefix="",
) -> Callable[[ImmutableMultiDict], dict[str, Any]]:
    def mkgetlist(name: str, hasdefault: bool):
        name = prefix + name

        def getlist(values: ImmutableMultiDict):
            if hasdefault and name not in values:
                return MISSING
            return values.getlist(name)

        return getlist

    def mkgetval(name: str, hasdefault: bool):
        name = prefix + name

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
            schema2 = schema["definitions"][getname(p["$ref"])]
            d = convert_from_schema(schema2, prefix=f"{prefix}{name}.")
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


def getname(s: str) -> str:
    return s.split("/")[-1]


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
                typ = getname(p["$ref"])
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


def flatten(json: dict[str, Any]) -> Iterator[tuple[str, Any]]:
    """flatten a nested dictionary into a top level dictionary with "dotted" keys"""
    for key, val in json.items():
        if isinstance(val, dict):
            for k, v in flatten(val):
                yield f"{key}.{k}", v
        else:
            yield key, val


class VE(BaseModel):
    msg: str


class Api:
    def __init__(self, name: str | None = None):
        self.dataclasses: set[type[BaseModel]] = set()
        self.builder = TSBuilder()
        self.funcs: list[TSField] = []
        self.name = name

    def __call__(self, func=None, *, onexc=None):
        if func is None:
            return lambda func: self.api(func, onexc=onexc)
        return self.api(func, onexc=onexc)

    def api(self, func, *, onexc=None):
        ts = self.builder(func)
        ts = replace(ts, isasync=True)
        self.funcs.append(TSField(name=ts.name, type=ts.anonymous()))

        hints = get_type_hints(func)
        sig = signature(func)
        defaults = {
            k: v.default for k, v in sig.parameters.items() if v.default is not v.empty
        }
        cargs = {}

        def get_req_values():
            if not hasattr(g, "_ts_values"):
                g._ts_values = (
                    ImmutableMultiDict(dict(flatten(request.json)))
                    if request.is_json
                    else CombinedMultiDict([request.values, request.files])
                )
            return g._ts_values

        def getvalue(name: str, t: type[Any]) -> Any:
            values = get_req_values()
            return t(values.get(name)) if name in values else MISSING

        def getlistvalue(name: str, t: type[Any], arg: type[Any]) -> Any:
            values = get_req_values()
            if name not in values and name in defaults:
                return MISSING
            ret = values.getlist(name)
            # catch ValueError?
            return t(arg(v) for v in ret)

        def cvt(name: str, typ: type[Any]) -> None:
            if hasattr(typ, "__args__"):
                # e.g. list[int]
                if len(typ.__args__) > 1:
                    raise ValueError(f"can't do multi arguments {name}")
                arg = typ.__args__[0]
                if arg == FileStorage:
                    arg = lambda v: v

                cargs[name] = lambda: getlistvalue(name, typ, arg)

            elif issubclass(typ, BaseModel):
                convert = converter(typ)
                self.dataclasses.add(typ)
                cargs[name] = lambda: convert(get_req_values())
            else:
                if typ == FileStorage:
                    typ = lambda v: v  # type: ignore
                cargs[name] = lambda: getvalue(name, typ)

        # npy = 0
        # for name, t in hints.items():
        #     if name == "return":
        #         continue
        #     if issubclass(t, BaseModel):
        #         npy +=1

        for name, t in hints.items():
            if name == "return":
                continue
            cvt(name, t)

        asjson = "return" in hints and issubclass(hints["return"], BaseModel)
        if asjson:
            self.dataclasses.add(hints["return"])

        del hints
        del ts

        @wraps(func)
        def api_func(*args, **kwargs):
            args = {}
            try:
                for name, cvt in cargs.items():
                    v = cvt()
                    if v is not MISSING:
                        args[name] = v
                kwargs.update(args)
                ret = func(**kwargs)
                if asjson:
                    if not isinstance(ret, BaseModel):
                        raise ValueError(
                            f"type signature for {func.__name__} returns a pydantic instance, but we have {ret}",
                        )
                    ret = make_response(ret.json())
                    ret.headers["Content-Type"] = "application/json"
                return ret
            except ValidationError as e:
                if onexc is not None:
                    return onexc(e)
                return self.onexc(e)

            except ValueError as e:
                if onexc is not None:
                    return onexc(e)
                return self.onexc(VE(msg=str(e)))

        return api_func  # type: ignore

    def onexc(self, e: ValidationError | VE) -> Response:
        ret = make_response(e.json(), 400)
        ret.headers["Content-Type"] = "application/json"
        return ret

    def to_ts(self, name: str = "App", file=sys.stdout) -> None:
        self.show_dataclasses(self.dataclasses, file=file)
        self.show_interface(name, file=file)

    def show_interface(self, name: str, file=sys.stdout) -> None:
        interface = TSInterface(name=name, fields=self.funcs)
        print(interface, file=file)
        # for build_func in self.builder.process_seen():
        #     print(build_func())

    @classmethod
    def show_dataclasses(
        cls,
        dataclasses: set[type[BaseModel]],
        file=sys.stdout,
    ) -> None:
        seen: set[str] = set()
        for model in dataclasses:
            print(to_ts(model, seen), file=file)

    def show_api(self, app: Flask, file=sys.stdout) -> None:
        self.to_ts(self.name or app.name.split(".")[-1].title(), file=sys.stdout)

    def init_app(self, app: Flask) -> None:
        if "flask-typescript" not in app.extensions:
            app.extensions["flask-typescript"] = set()

            @app.cli.command("api")
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
                d = app.extensions["flask-typescript"]
                appname = app.name.split(".")[-1].title()
                dataclasses = set()
                for api in d:
                    dataclasses |= api.dataclasses

                if out is not None:
                    with open(out, "w") as fp:
                        Api.show_dataclasses(dataclasses=dataclasses, file=fp)
                        if not without_interface:
                            for api in d:
                                api.show_interface(self.name or appname, file=fp)
                else:
                    Api.show_dataclasses(dataclasses=dataclasses)
                    if not without_interface:
                        for api in d:
                            api.show_interface(self.name or appname)

        d = app.extensions["flask-typescript"]
        d.add(self)
