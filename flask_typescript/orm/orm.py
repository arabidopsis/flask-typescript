from __future__ import annotations

import re
from typing import Any
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

from ..dc import DataColumn
from ..dc import metadata_to_ts
from ..typing import Annotation
from ..typing import INDENT
from ..typing import MISSING
from ..typing import TSBuilder
from ..typing import TSTypeable
from ..utils import lenient_issubclass
from .meta import Base
from .meta import BaseDC
from .meta import DCBase
from .meta import get_type_hints_sqla

if TYPE_CHECKING:
    from sqlalchemy.engine.url import URL


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


CLEAN = re.compile(r'[/\'"()]+')


def model_defaults(model: type[DeclarativeBase]) -> dict[str, Any]:
    columns = model.__table__.columns
    ret = {}
    for c in columns:
        if c.default is not None:
            if c.default.is_scalar:
                ret[c.key] = c.default.arg
    return ret


def chop(s: str) -> str:
    for q in ['"', "'"]:
        if s.startswith(q) and s.endswith(q):
            return s[1:-1]
    return s


def model_metadata(model: type[DeclarativeBase]) -> dict[str, DataColumn]:
    columns = model.__table__.columns
    ret = {}
    for c in columns:
        default = c.default
        if callable(default):
            default = default()
        if default is None:
            if c.server_default:
                d = c.server_default
                if hasattr(d, "arg"):
                    # e.g. text("0")
                    default = chop(str(d.arg))
                else:
                    default = "$SERVER_DEFAULT$"
        else:
            default = str(default)
        typ = c.type
        name = CLEAN.sub("", c.key).replace(" ", "_")
        if name[0].isdigit():
            name = "_" + name

        d = {
            "name": c.key,
            "primary_key": c.primary_key,
            "nullable": c.nullable,
            "default": default,
        }
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
