from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from typing import TextIO
from typing import TYPE_CHECKING

from sqlalchemy import create_engine
from sqlalchemy import Date
from sqlalchemy import DateTime
from sqlalchemy import Enum
from sqlalchemy import Integer
from sqlalchemy import JSON
from sqlalchemy import LargeBinary
from sqlalchemy import MetaData
from sqlalchemy import Numeric
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import TIMESTAMP
from sqlalchemy.dialects.mysql import SET
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import DeclarativeMeta
from sqlalchemy.sql.sqltypes import _Binary

from .meta import Base
from .meta import BaseDC
from .meta import DCBase
from .meta import get_type_hints_sqla
from flask_typescript.typing import Annotation
from flask_typescript.typing import INDENT
from flask_typescript.typing import MISSING
from flask_typescript.typing import NL
from flask_typescript.typing import TSBuilder
from flask_typescript.typing import TSTypeable
from flask_typescript.utils import lenient_issubclass

if TYPE_CHECKING:
    from sqlalchemy.engine.url import URL

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

MAP = {
    "text": "string",
    "integer": "number",
    "float": "number",
    "boolean": "boolean",
    "binary": "string // binary",
    "date": "string",
    "datetime": "string",
    "timestamp": "string",
    "json": "unknown",
    "any": "unknown",
}


def is_model(v) -> bool:
    return lenient_issubclass(v, DeclarativeBase)  # or isinstance(v, DeclarativeMeta)


@dataclass
class DataColumn:
    name: str
    type: TYPE = "text"
    nullable: bool = False
    primary_key: bool = False
    multiple: bool = False
    values: list[str] | None = None
    maxlength: int = -1

    def _bool(self, name: str) -> str:
        return f"{name}: {str(getattr(self,name)).lower()}"

    def _attr(self, name: str) -> str:
        val = getattr(self, name)
        return f"{name}: {val}"

    def _str(self, name: str) -> str:
        return f'{name}: "{getattr(self,name)}"'

    def to_ts(self, prefix="") -> str:
        name = self._str("name")
        typ = self._str("type")
        primary_key = self._bool("primary_key")
        multiple = self._bool("multiple")
        nullable = self._bool("nullable")
        if self.maxlength > 0:
            maxlength = self._attr("maxlength")
        else:
            maxlength = None
        values = "null" if self.values is None else repr(self.values)
        values = f"values: {values}"

        tab = prefix + INDENT
        attr = [name, typ, nullable, primary_key, multiple, values, maxlength]
        ret = f",{NL}{tab}".join(a for a in attr if a is not None)
        return f"{{{NL}{tab}{ret}{NL}{prefix}}}"

    def __str__(self):
        return self.to_ts()


CLEAN = re.compile(r'[/\'"()]+')

from typing import Any


def model_defaults(model: type[DeclarativeBase]) -> dict[str, Any]:
    columns = model.__table__.columns
    ret = {}
    for c in columns:
        if c.default is not None:
            if c.default.is_scalar:
                ret[c.key] = c.default.arg
    return ret


def model_metadata(model: type[DeclarativeBase]) -> dict[str, DataColumn]:
    columns = model.__table__.columns
    ret = {}
    for c in columns:
        typ = c.type
        name = CLEAN.sub("", c.key).replace(" ", "_")
        if name[0].isdigit():
            name = "_" + name

        d = {"name": c.key, "primary_key": c.primary_key, "nullable": c.nullable}
        if isinstance(typ, SET):
            ret[name] = DataColumn(
                values=list(typ.values),
                multiple=True,
                type="text",
                **d,
            )

        elif isinstance(typ, Enum):  # before String
            ret[name] = DataColumn(values=list(typ.enums), type="text", **d)
        elif isinstance(typ, (String, Text)):
            ret[name] = DataColumn(maxlength=typ.length or 0, type="text", **d)
        elif isinstance(typ, Integer):
            ret[name] = DataColumn(type="integer", **d)
        elif isinstance(typ, Numeric):
            ret[name] = DataColumn(type="float", **d)
        elif isinstance(typ, (LargeBinary, _Binary)):
            ret[name] = DataColumn(type="binary", maxlength=typ.length or -1, **d)
        elif isinstance(typ, Date):
            ret[name] = DataColumn(type="date", **d)
        elif isinstance(typ, TIMESTAMP):
            ret[name] = DataColumn(type="timestamp", **d)
        elif isinstance(typ, DateTime):
            ret[name] = DataColumn(type="datetime", **d)
        elif isinstance(typ, JSON):
            ret[name] = DataColumn(type="json", **d)
        else:
            ret[name] = DataColumn(type="any", **d)
    return ret


def model_to_ts(name: str, meta: dict[str, DataColumn]) -> str:
    out = [f"export type {name}Type = {{"]
    for k, v in meta.items():
        type = MAP[v.type]
        if v.values:
            type = " | ".join(f'"{v}"' for v in v.values)
            if v.multiple:
                type = f"({type})[]"
        s = f"{INDENT}{k}: {type}"
        out.append(s)
    out.append("}")

    return "\n".join(out)


def metadata_to_ts(name: str, meta: dict[str, DataColumn]) -> str:
    out = [f"export const {name} = {{"]
    for k, v in meta.items():
        s = f"{INDENT}{k}: {v.to_ts(INDENT)},"
        out.append(s)
    out.append("} satisfies Readonly<Record<string, DataColumn>>")

    return "\n".join(out)


def datacolumn(out: TextIO):
    builder = TSBuilder(ignore_defaults=True)
    b = builder(DataColumn).to_ts()
    b = b.replace("maxlength:", "maxlength?:")  # HACK!
    print(b, file=out)


def dodatabase(url: str | URL, *tables: str, preamble: bool = True, out: TextIO):
    if preamble:
        datacolumn(out)
    engine = create_engine(url)
    meta = MetaData()
    if not tables:
        meta.reflect(bind=engine)
    else:
        meta.reflect(bind=engine, only=list(tables))

    for table in meta.tables.values():
        name = table.name.title()
        try:

            class M(Base):
                __clsname__ = name
                __table__ = table

        except ArgumentError as e:
            # no primary key maybe ...
            print(f"// Error for {table.name}: {e}", file=out)
            continue
        m = model_metadata(M)
        print(model_to_ts(name, m), file=out)
        print(metadata_to_ts(name, m), file=out)


def get_annotations(cls: type[DeclarativeBase]) -> dict[str, Annotation]:
    d = get_type_hints_sqla(cls)
    defaults = model_defaults(cls)
    ret = {k: Annotation(k, v, defaults.get(k, MISSING)) for k, v in d.items()}
    return ret


class ModelBuilder(TSBuilder):
    def get_annotations(self, cls: TSTypeable) -> dict[str, Annotation]:
        if is_model(cls):
            return get_annotations(cls)  # type: ignore
        return super().get_annotations(cls)


def model_ts(*Models: type[DCBase], out: TextIO):
    builder = ModelBuilder()
    # seen = set()
    for Model in Models:
        v = builder(Model)
        # seen.add(v.name)
        print(v, file=out)

    # for n in seen:
    #     if n in builder.seen:
    #         builder.seen.pop(n)
    for b in builder.process_seen():
        try:
            print(b(), file=out)
        except AttributeError as e:
            print(f"// {e}", file=out)


def find_models(module: str):
    from importlib import import_module
    from .meta import Base, BaseDC, BasePY, DeclarativeBase, Meta, MetaDC

    exclude = {Base, BaseDC, BasePY, DeclarativeBase, Meta, MetaDC, DeclarativeMeta}

    m = import_module(module)
    if m is None:
        return
    for v in m.__dict__.values():
        if is_model(v):
            if v in exclude:
                continue
            yield v


def model_meta_ts(*Models: type[BaseDC], preamble: bool = True, out: TextIO):
    if preamble:
        datacolumn(out)
    for Model in Models:
        name = Model.__name__
        if not hasattr(Model, "__table__"):

            class M(Model):  # type: ignore
                __clsname__ = name.title()
                __tablename__ = name

            m = model_metadata(M)
        else:
            m = model_metadata(Model)

        print(metadata_to_ts(name, m), file=out)
