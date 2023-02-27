from __future__ import annotations

from functools import wraps
from typing import Any
from typing import Callable
from typing import get_type_hints

from flask import jsonify
from flask import request
from pydantic import BaseModel
from pydantic import ValidationError
from werkzeug.datastructures import ImmutableMultiDict


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

            return f"{typ}{islist}"

        for name, p in definitions.items():
            typ = gettype(p)
            if "default" in p:
                q = "?"
            else:
                q = ""
            row = f"{name}{q}: {typ};"
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

    s = f"""export type {schema['title']} {{
    {attrs}
}}"""
    out.append(s)
    return "\n".join(out)


MISSING = object()


class Api:
    def __init__(self):
        self.dataclasses = set()

    def __call__(self, func):
        return self.api(func)

    def api(self, func):
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
                    ret = jsonify(ret.json())
                return ret
            except ValidationError as e:
                ret = jsonify(e.json())
                ret.status_code = 400
                return ret

        return myfunc

    def to_ts(self):
        for model in self.dataclasses:
            print(to_ts(model))
