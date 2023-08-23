from __future__ import annotations

import json
import re
from contextlib import contextmanager
from importlib.resources import read_text
from typing import Any
from typing import Callable
from typing import Generator
from typing import IO
from typing import Iterator

from pydantic_core import ErrorDetails
from pydantic_core import to_jsonable_python
from werkzeug.datastructures import MultiDict


ARG = re.compile(r"\[([^]]*)\]")


def lenient_issubclass(
    cls: Any,
    class_or_tuple: type[Any] | tuple[type[Any], ...] | None,
) -> bool:
    return isinstance(cls, type) and issubclass(cls, class_or_tuple)  # type: ignore[arg-type]


def flatten(json: Iterator[tuple[str, Any]]) -> Iterator[tuple[str, Any]]:
    """flatten a nested dictionary into a top level dictionary with "dotted" keys"""
    for key, val in json:
        if isinstance(val, dict):
            for k, v in flatten((k, v) for k, v in val.items()):
                yield f"{key}.{k}", v
        else:
            yield key, val


def unflatten(md: MultiDict[str, Any]) -> dict[str, Any]:
    ret: dict[str, Any] = {}
    for key, val in md.items(multi=True):
        if key in ret:
            v = ret[key]
            if isinstance(v, list):
                v.append(val)
            else:
                ret[key] = [v, val]
        else:
            ret[key] = val

    return ret


def dedottify(json: dict[str, Any], recursive: bool = False) -> dict[str, Any]:
    """undottify keys"""
    # {'a.b':1, 'a.c':2 , 'a.d': 3} => {a: {b:1,c:2, d:3}}
    ret: dict[str, Any] = {}
    for key, val in json.items():
        if recursive and isinstance(val, dict):
            val = dedottify(val, recursive=recursive)
        if "." in key:
            *keylist, last = key.split(".")
            tgt = ret
            for k in keylist:
                if k not in tgt:
                    tgt[k] = {}
                tgt = tgt[k]
                if not isinstance(tgt, dict):
                    raise ValueError(f"{key} inconsitent dotted key")
            tgt[last] = val
        else:
            ret[key] = val
    return ret


# jquery keys are like:
# see jQuery.param: https://github.com/jquery/jquery/blob/main/src/serialize.js#L55

# draw: 6
# columns[0][data]: protein_name
# columns[0][name]:
# columns[0][searchable]: true
# columns[0][orderable]: true
# columns[0][search][value]:
# columns[0][search][regex]: false


def ijquery_keys(key: str) -> Iterator[str]:
    start = 0
    for m in ARG.finditer(key):
        prev = key[start : m.start()]
        if prev:
            yield prev
        yield m.group(1)
        start = m.end()
    prev = key[start:]
    if prev:
        yield prev


def jquery_keys(key: str) -> list[str]:
    return list(ijquery_keys(key))


# names that are just [0] are invalid e.g.:
# [0]: val1
# [1]: val2
def jquery_json(form: MultiDict[str, Any]) -> dict[str, Any]:
    ret: dict[str, Any] = {}

    def ensure(lst: Any, idx: int) -> None:
        if not isinstance(lst, list):
            raise ValueError("inconsitent keys")
        while len(lst) <= idx:
            lst.append({})

    for fullkey, val in form.items(multi=True):
        keylist = jquery_keys(fullkey)
        tgt = ret
        prefix, key = keylist[:-1], keylist[-1]
        if len(prefix) == 0 and key.isdigit():
            raise ValueError(f"illegal key {fullkey}")
        for k, nxt in zip(prefix, keylist[1:]):
            if k == "":  # from a[]
                k = str(len(tgt))
            if k.isdigit():
                i = int(k)
                ensure(tgt, i)
                tgt = tgt[i]  # type: ignore
            else:
                if k not in tgt:
                    tgt[k] = [] if nxt.isdigit() or nxt == "" else {}
                tgt = tgt[k]

        if key == "":  # from a[]
            key = str(len(tgt))
        if key.isdigit():
            i = int(key)
            ensure(tgt, i)
            tgt[i] = val  # type: ignore
        else:
            tgt[key] = val
    return ret


def jquery_form(form: MultiDict[str, Any]) -> dict[str, Any]:
    """Turn a jquery form dictionary into a dotted dictionary"""
    return dedottify(jquery_json(form))


def multidict_json(form: MultiDict[str, Any]) -> dict[str, Any]:
    return dedottify(unflatten(form))


def getdict(values: dict[str, Any], path: list[str] | None = None) -> dict[str, Any]:
    if path is None:
        return values
    for attr in path:
        if attr in values:
            values = values[attr]
            if not isinstance(values, dict):
                raise ValueError(f"{'.'.join(path)}: bad path")
        else:
            return {}
    return values


CamelCase = re.compile(r"(?<!^)(?=[A-Z])")


def tojson(v: Any, indent: None | int | str = 2) -> str:
    return json.dumps(v, indent=indent, default=to_jsonable_python)


class FlaskValueError(ValueError):
    """Create an Error similar to pydantic's ValidationError"""

    def __init__(
        self,
        msg: str,
        loc: str,
        errtype: str = "malformed",
        exc_name: str = "value_error",
    ) -> None:
        super().__init__()
        self.msg = msg
        self.loc = loc
        self.errtype = errtype
        self.exc_name = exc_name

    # @property
    # def exc_name(self) -> str:
    #     return CamelCase.sub("_", self.exc.__class__.__name__).lower()

    def json(self, *, indent: None | int | str = 2) -> str:
        return tojson(self.errors(), indent=indent)

    def errors(self) -> list[ErrorDetails]:
        return [
            dict(
                loc=(self.loc,),
                msg=str(self.msg),
                type=f"{self.exc_name}.{self.errtype}",
                input=None,
            ),
        ]


@contextmanager
def maybeclose(out: str | None, mode: str = "rt") -> Generator[IO[str], None, None]:
    import sys

    if out:
        fp = open(out, mode)
        close = True
    else:
        fp = sys.stdout
        close = False
    try:
        yield fp
    finally:
        if close:
            fp.close()


def unwrap(func: Callable[..., Any]) -> Callable[..., Any]:
    while hasattr(func, "__wrapped__"):
        func = func.__wrapped__
    return func


def get_preamble() -> str:
    return read_text("flask_typescript", "preamble.ts")
    # path = Path(__file__).parent / "preamble.ts"
    # with open(path, "rt") as fp:
    #     return fp.read()


def is_literal(typ: type[Any]) -> bool:
    return typ.__class__.__name__ == "_LiteralGenericAlias"
