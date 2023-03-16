from __future__ import annotations

import json
from dataclasses import MISSING
from dataclasses import replace
from functools import wraps
from typing import Any
from typing import Callable
from typing import get_type_hints
from typing import Iterator

from flask import Flask
from flask import g
from flask import jsonify
from flask import make_response
from flask import request
from pydantic import BaseModel
from pydantic import ValidationError
from werkzeug.datastructures import CombinedMultiDict
from werkzeug.datastructures import FileStorage
from werkzeug.datastructures import ImmutableMultiDict

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
    ret = {}

    def getlist(name: str, values: ImmutableMultiDict, hasdefault: bool):
        name = prefix + name
        if hasdefault and name not in values:
            return MISSING
        return values.getlist(name)

    def getval(name: str, values: ImmutableMultiDict, hasdefault: bool):
        return values.get(prefix + name, MISSING)

    def mkconvert(d):
        def convert(name, values: ImmutableMultiDict, hasdefault: bool):
            return d(values)

        return convert

    required = set(schema.get("required", []))

    for name, p in schema["properties"].items():
        hasdefault = name not in required
        if "$ref" in p:
            mname = schema["definitions"][getname(p["$ref"])]
            d = convert_from_schema(mname, prefix=f"{prefix}{name}.")
            ret[name] = mkconvert(d), hasdefault
            continue

        typ = p["type"]
        if typ == "array":
            ret[name] = getlist, hasdefault
        else:
            ret[name] = getval, hasdefault

    def convert(values: ImmutableMultiDict) -> dict[str, Any]:
        args = {}
        for name, (cvt, hasdefault) in ret.items():
            v = cvt(name, values, hasdefault)
            if v is MISSING:
                continue
            args[name] = v
        return args

    return convert


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


def repr(v):
    return json.dumps(v)


def getname(s: str) -> str:
    return s.split("/")[-1]


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
    attrs = "\t" + "\n\t".join(ret)

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


class Api:
    def __init__(self, name: str | None = None):
        self.dataclasses: set[type[BaseModel]] = set()
        self.builder = TSBuilder()
        self.funcs: list[TSField] = []
        self.name = name

    def __call__(self, func):
        return self.api(func)

    def api(self, func):
        ts = self.builder(func)
        ts = replace(ts, isasync=True)
        self.funcs.append(TSField(name=ts.name, type=ts.anonymous()))

        hints = get_type_hints(func)
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
                ret = make_response(e.json(), 400)
                ret.headers["Content-Type"] = "application/json"
                return ret
            except ValueError as e:
                ret = jsonify(dict(status="failed", msg=str(e)))
                ret.status_code = 500
                ret.headers["Content-Type"] = "application/json"
                return ret

        return api_func  # type: ignore

    def to_ts(self, name: str = "App") -> None:
        seen: set[str] = set()
        for model in self.dataclasses:
            print(to_ts(model, seen))
        interface = TSInterface(name=name, fields=self.funcs)
        print(interface)
        # for build_func in self.builder.process_seen():
        #     print(build_func())

    def show_api(self, app: Flask) -> None:
        self.to_ts(self.name or app.name.split(".")[-1].title())

    def init_app(self, app: Flask) -> None:
        if "flask-typescript" not in app.extensions:
            app.extensions["flask-typescript"] = set()

            @app.cli.command("api")
            # @click.argument("name")
            def show_api():
                d = app.extensions["flask-typescript"]
                for api in d:
                    api.show_api(app)

        d = app.extensions["flask-typescript"]
        d.add(self)
