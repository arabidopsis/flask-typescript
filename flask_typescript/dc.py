from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .typing import INDENT
from .typing import NL

TYPE = Literal[
    "text",
    "integer",
    "float",
    "boolean",
    "binary",
    "date",
    "datetime",
    "timestamp",
    "json",
    "any",
]


def dc_to_ts(self: DataColumn, prefix="") -> str:
    def _bool(name: str) -> str:
        return f"{name}: {str(getattr(self,name)).lower()}"

    def _attr(name: str) -> str:
        val = getattr(self, name)
        return f"{name}: {val}"

    def _str(name: str) -> str:
        return f'{name}: "{getattr(self,name)}"'

    def to_ts() -> str:
        name = _str("name")
        typ = _str("type")
        primary_key = _bool("primary_key")
        multiple = _bool("multiple")
        nullable = _bool("nullable")
        default = _str("default") if self.default else None
        if self.maxlength > 0:
            maxlength = _attr("maxlength")
        else:
            maxlength = None
        values = "null" if self.values is None else repr(self.values)
        values = f"values: {values}"

        tab = prefix + INDENT
        attr = [name, typ, nullable, primary_key, multiple, values, default, maxlength]
        ret = f",{NL}{tab}".join(a for a in attr if a is not None)
        return f"{{{NL}{tab}{ret}{NL}{prefix}}}"

    return to_ts()


@dataclass
class DataColumn:
    name: str
    type: TYPE = "text"
    nullable: bool = False
    primary_key: bool = False
    multiple: bool = False
    values: list[str] | None = None
    default: str | None = None
    maxlength: int = -1

    def _bool(self, name: str) -> str:
        return f"{name}: {str(getattr(self,name)).lower()}"

    def _attr(self, name: str) -> str:
        val = getattr(self, name)
        return f"{name}: {val}"

    def _str(self, name: str) -> str:
        return f'{name}: "{getattr(self,name)}"'

    def to_ts(self, prefix="") -> str:
        return dc_to_ts(self, prefix)

    def __str__(self):
        return self.to_ts()


def metadata_to_ts(name: str, meta: dict[str, DataColumn]) -> str:
    out = [f"export const {name} = {{"]
    for k, v in meta.items():
        s = f"{INDENT}{k}: {v.to_ts(INDENT)},"
        out.append(s)
    out.append("} satisfies Readonly<Record<string, DataColumn>>")

    return "\n".join(out)
