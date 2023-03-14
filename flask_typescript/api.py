from __future__ import annotations

import json
from functools import wraps
from typing import Any
from typing import Callable
from typing import get_type_hints

from flask import Flask
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
    for name, p in model.schema()["properties"].items():
        if p["type"] == "array":
            ret[name] = lambda name, values: values.getlist(name)
        else:
            ret[name] = lambda name, values: values.get(name)

    def convert(values: ImmutableMultiDict) -> BaseModel:
        args = {}
        for name, cvt in ret.items():
            if name not in values:
                continue
            args[name] = cvt(name, values)
        return model(**args)

    return convert


def to_ts(model: type[BaseModel]) -> str:
    schema = model.schema()
    return to_ts_schema(schema)


def repr(v):
    return json.dumps(v)


def to_ts_schema(schema: dict[str, Any]) -> str:
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
            s = to_ts_schema(d)
            out.append(s)

    ret = props(schema["properties"])
    attrs = "\t" + "\n\t".join(ret)

    s = f"""export type {schema['title']} = {{
{attrs}
}}"""
    out.append(s)
    return "\n".join(out)


MISSING = object()


class Api:
    def __init__(self):
        self.dataclasses = set()
        self.builder = TSBuilder()
        self.funcs = []

    def __call__(self, func):
        return self.api(func)

    def api(self, func):
        ts = self.builder(func)
        self.funcs.append(TSField(name=ts.name, type=ts.anonymous()))

        hints = get_type_hints(func)
        cargs = {}

        def getvalues():
            return request.json if request.is_json else request.values

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

    def to_ts(self):
        for model in self.dataclasses:
            print(to_ts(model))

        interface = TSInterface(name="App", fields=self.funcs)
        print(interface)
        for build_func in self.builder.process_seen():
            print(build_func())

    def init_app(self, app: Flask) -> None:
        if "flask-typescript" not in app.extensions:
            app.extensions["flask-typescript"] = {}
