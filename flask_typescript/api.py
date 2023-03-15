from __future__ import annotations

import json
from dataclasses import replace
from functools import wraps
from typing import Any
from typing import Callable
from typing import get_type_hints

from flask import Flask
from flask import g
from flask import make_response
from flask import request
from pydantic import BaseModel
from pydantic import ValidationError
from werkzeug.datastructures import ImmutableMultiDict

from .typing import TSBuilder
from .typing import TSField
from .typing import TSInterface


def converter(model: type[BaseModel]) -> Callable[[ImmutableMultiDict], BaseModel]:
    ret = {}

    def getlist(name: str, values: ImmutableMultiDict, hasdefault: bool):
        if hasdefault and name not in values:
            return None
        return values.getlist(name)

    def getval(name: str, values: ImmutableMultiDict, hasdefault: bool):
        return values.get(name)

    schema = model.schema()
    required = set(schema.get("required", []))

    for name, p in schema["properties"].items():
        typ = p["type"]
        hasdefault = name not in required
        if typ == "array":
            ret[name] = getlist, hasdefault
        else:
            ret[name] = getval, hasdefault

    def convert(values: ImmutableMultiDict) -> BaseModel:
        args = {}
        for name, (cvt, hasdefault) in ret.items():
            v = cvt(name, values, hasdefault)
            if v is None:
                continue
            args[name] = v
        return model(**args)

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


def to_ts_schema(schema: dict[str, Any], seen: set[str]) -> str:
    def props(definitions):
        ret = []

        def gettype(p):
            if "$ref" in p:
                typ = p["$ref"].split("/")[-1]
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


MISSING = object()


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

        def getvalues():
            if not hasattr(g, "_ts_values"):
                g._ts_values = (
                    ImmutableMultiDict(request.json)
                    if request.is_json
                    else request.values
                )
            return g._ts_values

        def getvalue(name, t):
            values = getvalues()
            return t(values.get(name)) if name in values else MISSING

        def cvt(name, t):
            if issubclass(t, BaseModel):
                convert = converter(t)
                self.dataclasses.add(t)
                cargs[name] = lambda: convert(getvalues())
            else:
                cargs[name] = lambda: getvalue(name, t)

        for name, t in hints.items():
            if name == "return":
                continue
            cvt(name, t)

        asjson = "return" in hints and issubclass(hints["return"], BaseModel)

        @wraps(func)
        def myfunc(*args, **kwargs):
            args = {}
            try:
                for name, cvt in cargs.items():
                    v = cvt()
                    if v is not MISSING:
                        args[name] = v

                kwargs.update(args)
                ret = func(**kwargs)
                if asjson:
                    ret = make_response(ret.json())
                    ret.headers["Content-Type"] = "application/json"
                return ret
            except ValidationError as e:
                ret = make_response(e.json(), 400)
                ret.headers["Content-Type"] = "application/json"
                return ret

        return myfunc

    def to_ts(self, name: str = "App"):
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
