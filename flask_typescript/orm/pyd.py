from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from typing import get_args
from typing import get_type_hints
from typing import IO

from jinja2 import Template
from sqlalchemy import ColumnDefault
from sqlalchemy.orm import DeclarativeBase

from ..utils import lenient_issubclass

PY_TEMPLATE = Template(
    """
class {{name}}(BaseModel):
{%- for k,v in columns.items() %}
    {{k}}: {{v[0]}}{%if v[1] %} = {{v[1]}}{% endif %}
{%- endfor %}
""",
)


def tos(a: Any) -> str:
    if a.__module__ in {"builtins"}:
        if a.__name__ in {"list", "set"}:
            return f"{a.__name__}[{tos(get_args(a)[0])}]"
        return f"{a.__name__}"
    if a.__module__ in {"types", "typing"}:
        return str(a)
    if lenient_issubclass(a, DeclarativeBase):
        return f"{a.__name__}"
    if a.__module__ == "__main__":
        return f"{a.__name__}"
    return f"{a.__module__}.{a.__name__}"


def gettypes(dc: type[DeclarativeBase]) -> set[str]:
    def g(args: Any) -> Any:
        istype = isinstance(args, type)
        if istype and args.__module__ not in {"builtins"}:
            yield args.__module__
            return

        if hasattr(args, "__module__") and args.__module__ in {"typing"}:
            yield args.__module__

        for a in get_args(args):
            yield from g(a)

    s: set[Any] = set()
    for typ in get_type_hints(dc).values():
        s.update(g(typ))
    return s


def get_defaults(dc: type[DeclarativeBase]) -> dict[str, Any]:
    ret = {}
    for k, v in get_type_hints(dc).items():
        prop = getattr(dc, k).property
        if not hasattr(prop, "columns"):
            continue
        v = prop.columns[0].default
        if isinstance(v, ColumnDefault):
            ret[k] = v.arg
    return ret


def sqla_to_py(dcs: Sequence[type[DeclarativeBase]], out: IO[str]) -> None:
    dcs = list(dcs)
    print("from __future__ import annotations", file=out)
    imports = {
        s for dc in dcs for s in gettypes(dc) if s not in {"builtins", "__main__"}
    }
    for v in imports:
        print(f"import {v}", file=out)
    print("from pydantic import BaseModel", file=out)

    def torepr(v: Any) -> str | None:
        if v is None:
            return v
        return repr(v)

    for dc in dcs:
        defaults = get_defaults(dc)
        columns = {
            k: (tos(get_args(v)[0]), torepr(defaults.get(k, None)))
            for k, v in get_type_hints(dc).items()
        }
        print(PY_TEMPLATE.render(name=dc.__name__, columns=columns), file=out)
