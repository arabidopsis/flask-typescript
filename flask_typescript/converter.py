from __future__ import annotations

from dataclasses import _MISSING_TYPE
from dataclasses import dataclass
from dataclasses import MISSING
from typing import Any
from typing import Callable

from .types import JsonDict
from .types import MaybeDict
from .types import MissingDict
from .types import ModelType
from .utils import FlaskValueError
from .utils import getdict


def converter(
    model: type[ModelType],
    *,
    path: list[str] | None = None,
    hasdefault: bool = False,
) -> Callable[[JsonDict], ModelType | _MISSING_TYPE]:
    """Complex converter necessitated by select problems (see note above)"""
    ret = convert_from_schema(model.schema(), hasdefault=hasdefault)

    cvt = Converter(model.__name__, ret, hasdefault=hasdefault)

    def convert(values: JsonDict) -> ModelType | _MISSING_TYPE:
        values = getdict(values, path)
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
    def mkgetlist(
        name: str,
        typ: Callable[[JsonDict], MissingDict] | None,
        hasdefault: bool,
    ):
        def getlist(values: JsonDict):
            if name not in values:
                if hasdefault:
                    return MISSING
                return []
            v = values[name]
            # **** all this to just check this!!!! ****
            if not isinstance(v, list):
                v = [v]
            if typ is None:
                return v

            def nomissing(m):
                ret = typ(m)
                if ret is MISSING:
                    raise FlaskValueError(ValueError("missing data"), loc=name)
                return ret

            return [nomissing(m) for m in v]

        return getlist

    def mkgetval(name: str, typ: str, hasdefault: bool):
        def getval(values: JsonDict):
            return values.get(name, MISSING)

        return getval

    def aschema(
        loc: Locator,
        hasdefault: bool,
    ) -> Converter:
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

        cvt.attrs = ret  # patch attributes!
        return cvt

    def subschemas(
        attrname: str | None,
        lst: list[Locator],
        hasdefault: bool,
    ) -> Callable[[JsonDict], MissingDict]:
        cvts = [aschema(locator, hasdefault) for locator in lst]

        def convert_anyOf(values: JsonDict) -> MissingDict:
            if attrname is not None:
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
                items = p["items"]
                if "type" in items:
                    ret[name] = mkgetlist(name, None, hasdefault2)
                else:
                    # list of pydantic...
                    locators = [locate_schema(items["$ref"])]
                    c = subschemas(None, locators, False)
                    ret[name] = mkgetlist(name, c, hasdefault2)
            else:
                ret[name] = mkgetval(name, typ, hasdefault2)

    return ret


class Converter:
    def __init__(
        self,
        typename: str,
        attrs: dict[str, Callable[[JsonDict], Any]] = {},
        hasdefault: bool = False,
        # path: list[str] | None = None, # current path
    ):
        self.typename = typename
        self.attrs = attrs
        self.hasdefault = hasdefault
        # self.path = path

    def convert(self, values: JsonDict) -> MaybeDict:
        # values = getdict(values, self.path)
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
