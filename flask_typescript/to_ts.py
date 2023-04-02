from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from .typing import INDENT
from .typing import NL

# UNUSED ....


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
    from .converter import locate_schema

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
