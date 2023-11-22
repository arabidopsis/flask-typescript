from __future__ import annotations

from dataclasses import MISSING
from typing import Any
from typing import cast
from typing import IO
from typing import Iterator
from typing import Sequence
from typing import TYPE_CHECKING

import click
from sqlalchemy import Column
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
from sqlalchemy import Table
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
from ..typing import TSBuilder
from ..typing import TSInterface
from ..typing import TSTypeable
from ..utils import lenient_issubclass
from .meta import Base
from .meta import DCBase
from .meta import get_type_hints_sqla
from .utils import chop
from .utils import jsname

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


def is_model(v: Any) -> bool:
    return lenient_issubclass(v, DeclarativeBase) and hasattr(
        v,
        "__table__",
    )  # or isinstance(v, DeclarativeMeta)


def model_defaults(model: type[DeclarativeBase]) -> dict[str, Any]:
    if not hasattr(model, "__table__"):
        return {}
    columns = model.__table__.columns
    ret = {}
    for c in columns:
        if c.default is not None:
            if c.default.is_scalar:
                ret[c.key] = c.default.arg
    return ret


def get_default(c: Column[Any]) -> Any:
    default: Any = c.default
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
    return default


def model_metadata(model: type[DeclarativeBase]) -> dict[str, DataColumn]:
    table: Table = cast(Table, model.__table__)
    columns = table.columns
    ret = {}
    for c in columns.values():
        default = get_default(c)
        typ = c.type
        name = jsname(c.key)

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
        ttype = MAP[v.type]
        if v.values:
            ttype = " | ".join(f'"{v}"' for v in v.values)
            if v.multiple:
                ttype = f"({ttype})[]"
        s = f"{INDENT}{k}: {ttype}"
        out.append(s)
    out.append("}")

    return "\n".join(out)


def datacolumn(out: IO[str]) -> None:
    builder = TSBuilder(ignore_defaults=True)
    b = builder(DataColumn).to_ts()
    b = b.replace("maxlength:", "maxlength?:")  # HACK!
    print(b, file=out)


def get_tables(url: str | URL, *tables: str) -> list[Table]:
    engine = create_engine(url)
    meta = MetaData()
    if not tables:
        meta.reflect(bind=engine)
    else:
        meta.reflect(bind=engine, only=list(tables))
    return list(meta.tables.values())


def dodatabase(
    url: str | URL,
    *tables: str,
    preamble: bool = True,
    out: IO[str],
) -> None:
    if preamble:
        datacolumn(out)

    table_ts(out, get_tables(url, *tables))


def table_ts(
    out: IO[str],
    tables: Sequence[Table],
    *,
    metadata_only: bool = False,
) -> None:
    for table in tables:
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
        if not metadata_only:
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


def model_ts(*Models: type[DeclarativeBase], out: IO[str]) -> None:
    builder = ModelBuilder()
    # seen = set()
    for Model in Models:
        v = builder(Model)
        if isinstance(v, TSInterface) and len(v.fields) == 0:
            continue
        # seen.add(v.name)
        print(v, file=out)

    # for n in seen:
    #     if n in builder.seen:
    #         builder.seen.pop(n)
    for b in builder.process_seen():
        try:
            res = b()
            if res is not None:
                print(res, file=out)
        except AttributeError as e:
            print(f"// {e}", file=out)


def find_all_models(*modules: str) -> Iterator[list[type[DeclarativeBase]]]:
    for mod1 in modules:
        if ":" in mod1:
            mod, func = mod1.split(":")
        else:
            mod, func = mod1, None
        yield list(find_models(mod, mapped=func))


def find_models(
    module: str,
    mapped: str | None = None,
) -> Iterator[type[DeclarativeBase]]:
    from importlib import import_module
    from .meta import PYBase, Meta, DCMeta, _DCBase

    exclude = {
        Base,
        DCBase,
        PYBase,
        DeclarativeBase,
        Meta,
        DCMeta,
        DeclarativeMeta,
        _DCBase,
    }
    try:
        m = import_module(module)
    except ModuleNotFoundError as e:
        raise click.ClickException(f"No module named '{module}'") from e

    if mapped is not None:
        if mapped in m.__dict__:
            a = m.__dict__[mapped]()
        else:
            raise click.ClickException(f'no function named "{mapped} in {module}')
    else:
        a = m.__dict__.values()
    for v in a:
        if is_model(v):
            if v in exclude:
                continue
            yield v


def model_meta_ts(*Models: type[DCBase], preamble: bool = True, out: IO[str]) -> None:
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
