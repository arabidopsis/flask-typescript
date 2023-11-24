from __future__ import annotations

from typing import Any
from typing import get_args
from typing import get_type_hints

from jinja2 import Template
from pydantic import BaseModel
from sqlalchemy import ColumnDefault
from sqlalchemy.orm import DeclarativeBase

from ..utils import lenient_issubclass

T = Template(
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
    return f"{a.__module__}.{a.__name__}"


def gettypes(dc: Any) -> set[Any]:
    def g(args: Any) -> Any:
        aa = get_args(args)
        if not aa:
            yield args
        for a in aa:
            if lenient_issubclass(a, BaseModel):
                yield a
                continue
            if type(a) is type:
                yield a
            elif a.__module__ in {"typing"}:
                yield a
            else:
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


def sqla_to_py(*dcs: type[DeclarativeBase]) -> None:
    print("from __future__ import annotations")

    imports = {s.__module__ for dc in dcs for s in gettypes(dc)}
    for v in imports:
        if v in {"builtins"}:
            continue
        print(f"import {v}")
    print("from pydantic import BaseModel")
    for dc in dcs:
        defaults = get_defaults(dc)
        columns = {
            k: (tos(get_args(v)[0]), defaults.get(k, None))
            for k, v in get_type_hints(dc).items()
        }
        print(T.render(name=dc.__name__, columns=columns))
