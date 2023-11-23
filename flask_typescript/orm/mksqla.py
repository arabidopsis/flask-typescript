from __future__ import annotations

import sys
from dataclasses import dataclass
from dataclasses import replace
from datetime import datetime
from typing import Any
from typing import IO

import sqlalchemy as sqla
from jinja2 import Template
from sqlalchemy import Column
from sqlalchemy import Index
from sqlalchemy import MetaData
from sqlalchemy import Table
from sqlalchemy.dialects import mysql
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.sqltypes import _Binary

from ..utils import read_text
from .utils import pascal_case
from .utils import pyname
from .utils import quote


PREAMBLE = Template(
    """from __future__ import annotations
{% for mod, name in pyimports %}
from {{mod}} import {{name}}
{%- endfor %}

{% if not abstract %}
from sqlalchemy.orm import DeclarativeBase

class {{base}}(DeclarativeBase):
    pass
{% endif %}
""",
)


NS = {"+": "watson", "-": "crick", "class": "class_"}


SQLA = "sqlalchemy"
MYSQL = "sqlalchemy.dialects.mysql"
POSTGRES = "sqlalchemy.dialects.postgresql"


def get_template() -> str:
    return read_text("flask_typescript.orm", "sqlalchemy.py.jinja")


@dataclass
class ColumnInfo:
    name: str
    column_name: str
    type: str
    python_type: str
    nullable: bool
    pk: bool
    server_default: str | None
    index: bool | None
    unique: bool
    max_length: int | None


@dataclass
class TableInfo:
    model: str  # python class name
    tablename: str  # sql table name
    columns: list[ColumnInfo]
    charset: str | None
    indexes: set[Index]


class ModelMaker:
    def __init__(
        self,
        with_tablename: bool = False,
        abstract: bool = False,
        throw: bool = False,
        base: str = "Base",
        ns: dict[str, str] | None = None,
    ):
        if ns is None:
            ns = NS
        self.with_tablename = with_tablename
        self.abstract = abstract
        self.template = Template(get_template())
        self.base = base
        self.ns = ns
        self.throw = throw

    def convert_table(  # noqa: C901
        self,
        table: Table,
        enums: dict[tuple[str, ...], str],
        sets: dict[tuple[str, ...], str],
        pyimports: set[tuple[str, str]],
    ) -> TableInfo:
        columns: list[ColumnInfo] = []

        indexes = table.indexes
        sqlatype: str
        charset: str | None

        do = table.dialect_options.get("mysql")
        if do:
            charset = do["default charset"]
        else:
            charset = None

        for c in table.columns:
            typ = c.type
            sqlatype = name = typ.__class__.__name__
            pytype = "Any"
            server_default = None

            if c.server_default is not None:
                if hasattr(c.server_default, "arg"):
                    # e.g. text("0")
                    server_default = quote(str(c.server_default.arg))
                    server_default = f"text({server_default})"
                    pyimports.add((SQLA, "text"))

            if isinstance(typ, (sqla.Double, sqla.DOUBLE_PRECISION, mysql.DOUBLE)):
                pytype = "float"
                sqlatype = "Double"
                pyimports.add((SQLA, sqlatype))
            elif isinstance(typ, (sqla.Boolean, sqla.BOOLEAN)):
                sqlatype = "Boolean"
                pytype = "bool"
                pyimports.add((SQLA, sqlatype))
            elif isinstance(typ, (sqla.Float, sqla.REAL)):
                sqlatype = "Float"
                pytype = "float"
                pyimports.add((SQLA, sqlatype))
            elif isinstance(
                typ,
                (
                    sqla.Integer,
                    sqla.BigInteger,
                    sqla.SmallInteger,
                    sqla.INTEGER,
                    mysql.TINYINT,
                ),
            ):
                if name == "INTEGER":
                    name = "Integer"
                elif name == "BIGINT":
                    name = "BigInteger"
                elif name == "SMALLINT":
                    name = "SmallInteger"
                elif name == "TINYINT":
                    name = "Boolean"
                pytype = "int"
                sqlatype = name
                pyimports.add((SQLA, name))
            elif isinstance(typ, sqla.DECIMAL):
                sqlatype = f"DECIMAL({typ.precision},{typ.scale})"
                pytype = "Decimal"
                pyimports.add((SQLA, "DECIMAL"))
                pyimports.add(("decimal", "Decimal"))
            elif isinstance(typ, sqla.TIMESTAMP):
                pytype = "datetime"
                pyimports.add((SQLA, name))
                pyimports.add(("datetime", "datetime"))
            elif isinstance(typ, sqla.DateTime):
                pytype = "datetime"
                pyimports.add((SQLA, name))
                pyimports.add(("datetime", "datetime"))
            elif isinstance(typ, sqla.Date):
                pytype = "date"
                pyimports.add((SQLA, name))
                pyimports.add(("datetime", "date"))
            elif isinstance(typ, mysql.SET):
                s = tuple(typ.values)
                if s not in sets:
                    sets[s] = self.get_set_name(c, sets)
                sqlatype = sets[s]
                literal = f"Literal_{sqlatype}"
                pytype = f"set[{literal}]"
                pyimports.add((MYSQL, "SET"))
                pyimports.add(("typing", "Literal"))
                pyimports.add(("typing", "get_args"))
            elif isinstance(typ, sqla.Enum):
                s = tuple(typ.enums)
                if s not in enums:
                    enums[s] = self.get_enum_name(c, enums)
                sqlatype = enums[s]
                pytype = sqlatype
                sqlatype = f"Enum({sqlatype})"
                pyimports.add((SQLA, "Enum"))
                pyimports.add(("enum", "Enum as PyEnum"))
            elif isinstance(
                typ,
                (
                    sqla.Text,
                    mysql.TEXT,
                    mysql.MEDIUMTEXT,
                    mysql.TINYTEXT,
                    mysql.LONGTEXT,
                ),
            ):
                usecharset = False
                pytype = "str"
                if hasattr(typ, "charset") and typ.charset:
                    if typ.charset != charset:
                        usecharset = True
                        sqlatype = f'{name}(charset="{typ.charset}")'
                    else:
                        sqlatype = name
                else:
                    if name == "TEXT" and not usecharset:
                        name = "Text"
                    sqlatype = name
                if name.startswith(("TINY", "LONG", "MEDIUM")) or name == "TEXT":
                    pyimports.add((MYSQL, name))
                else:
                    pyimports.add((SQLA, name))

            elif isinstance(typ, (sqla.String, sqla.CHAR)):
                pytype = "str"
                if hasattr(typ, "charset") and typ.charset and typ.charset != charset:
                    sqlatype = f'{name}({typ.length}, charset="{typ.charset}")'
                    pyimports.add((MYSQL, name))
                else:
                    if name == "VARCHAR":
                        name = "String"
                    sqlatype = f"{name}({typ.length})"
                    pyimports.add((SQLA, name))
            elif isinstance(typ, (sqla.BLOB, mysql.LONGBLOB, mysql.MEDIUMBLOB)):
                pytype = "bytes"
                if name == "BLOB":
                    pyimports.add((SQLA, name))
                else:
                    pyimports.add((MYSQL, name))
            elif isinstance(typ, (sqla.BINARY, _Binary)):
                sqlatype = f"{name}({typ.length})"
                pytype = "bytes"
                pyimports.add((SQLA, name))
            elif isinstance(typ, (sqla.JSON, postgresql.JSONB)):
                pytype = "Any"
                if name == "JSON":
                    pyimports.add((SQLA, name))
                else:
                    pyimports.add((POSTGRES, name))
                pyimports.add(("typing", "Any"))
            elif isinstance(typ, mysql.YEAR):
                sqlatype = f"{name}(4)"
                pytype = "int"
                pyimports.add((MYSQL, name))
            elif isinstance(typ, sqla.ARRAY):
                item_type = typ.item_type.__class__.__name__
                dimensions = typ.dimensions or 1
                sqlatype = f"ARRAY({item_type}, dimensions={dimensions})"
                # TODO other array types?
                py_item_type = self.get_item_type(typ)
                pytype = f"list[{py_item_type}]"
                for _ in range(1, dimensions):
                    pytype = f"list[{pytype}]"
                pyimports.add((SQLA, "ARRAY"))
                pyimports.add((SQLA, item_type))
            elif isinstance(typ, postgresql.BYTEA):
                if typ.length:
                    sqlatype = f"{sqlatype}(length={typ.length})"
                pytype = "bytes"
                pyimports.add((POSTGRES, name))
            elif isinstance(typ, postgresql.HSTORE):
                pytype = "dict[str,str]"
                pyimports.add((POSTGRES, name))
            elif isinstance(typ, (mysql.BIT, postgresql.BIT)):
                if typ.length:
                    sqlatype = f"{sqlatype}(length={typ.length})"
                pytype = "bytes"
                pyimports.add((typ.__module__, name))

            else:
                sqlatype, pytype = self.other(c, pyimports)

            if c.nullable:
                pytype = f"{pytype} | None"

            max_length = c.type.length if hasattr(c.type, "length") else None

            d = ColumnInfo(
                name=c.name,
                type=sqlatype,
                python_type=pytype,
                nullable=c.nullable or False,
                pk=c.primary_key,
                server_default=server_default,
                index=c.index,
                unique=c.unique or False,
                column_name=self.column_name(c.name),
                max_length=max_length,
            )

            for i in indexes:
                if len(i.columns) == 1:
                    if c.name in i.columns:
                        d = replace(d, index=True, unique=i.unique)
                        indexes.remove(i)
                        break

            columns.append(d)

        if indexes:
            pyimports.add((SQLA, "Index"))

        return TableInfo(
            model=self.toclassname(table.name),
            tablename=table.name,
            columns=columns,
            charset=charset,
            indexes=indexes,
        )

    def get_item_type(self, typ: sqla.ARRAY) -> str:
        if isinstance(
            typ.item_type,
            (sqla.Integer, sqla.BigInteger, sqla.SmallInteger, sqla.INTEGER),
        ):
            return "int"
        if isinstance(typ.item_type, (sqla.Float, sqla.DOUBLE_PRECISION, sqla.Double)):
            return "float"
        return "str"

    def other(
        self,
        col: Column[Any],
        pyimports: set[tuple[str, str]],
    ) -> tuple[str, str]:
        if self.throw:
            raise RuntimeError(
                f'unknown field "{col.table.name}.{col.name}" {col.type}',
            )
        # make a guess and set python type to 'Any'
        name = col.type.__class__.__name__
        module = col.type.__class__.__module__
        sqlatype = name
        pytype = "Any"
        pyimports.add(("typing", "Any"))
        pyimports.add((module, name))
        return sqlatype, pytype

    def unique_name(self, name: str, names: set[str]) -> str:
        m = name
        i = 0
        while m in names:
            i += 1
            m = name + str(i)
        return m

    def get_enum_name(self, col: Column[Any], enums: dict[tuple[str, ...], str]) -> str:
        return self.unique_name(f"Enum_{col.key}", set(enums.values()))

    def get_set_name(self, col: Column[Any], sets: dict[tuple[str, ...], str]) -> str:
        return self.unique_name(f"Set_{col.key}", set(sets.values()))

    def toclassname(self, name: str) -> str:
        return pascal_case(self.pyname(name))

    def column_name(self, name: str) -> str:
        return self.pyname(name)

    def pyname(self, name: str) -> str:
        if self.ns and name in self.ns:
            return self.ns[name]
        return pyname(name)

    def __call__(self, tables: list[Table], out: IO[str] = sys.stdout) -> None:
        return self.run_tables(tables, out)

    def run_tables(
        self,
        tables: list[Table],
        out: IO[str] = sys.stdout,
    ) -> None:
        pyimports: set[tuple[str, str]] = {
            ("sqlalchemy.orm", "Mapped"),
            ("sqlalchemy.orm", "mapped_column"),
        }
        ret: list[str] = []
        sets: dict[tuple[str, ...], str] = {}
        enums: dict[tuple[str, ...], str] = {}
        for table in tables:
            tsets = sets.copy()
            tenums = enums.copy()
            data = self.convert_table(table, enums, sets, pyimports)

            xenums = [
                (enums[k], [(v, self.pyname(v)) for v in k])
                for k in set(enums.keys()) - set(tenums.keys())
            ]
            xsets = [(sets[k], k) for k in set(sets.keys()) - set(tsets.keys())]

            txt = self.template.render(
                sets=xsets,
                enums=xenums,
                base=self.base,
                abstract=self.abstract,
                schema=table.schema,
                with_tablename=self.with_tablename,
                table=data,
            )

            ret.append(txt)
        if sets:
            pyimports.add(("typing", "TypeAlias"))

        self.print_tables(
            ret,
            pyimports,
            out=out,
            base=self.base,
        )

    # def render_table(self, **data: Any) -> str:
    #     return self.template.render(**data)

    def print_tables(
        self,
        models: list[str],
        pyimports: set[tuple[str, str]],
        out: IO[str] = sys.stdout,
        base: str = "Base",
    ) -> None:
        def key(p: tuple[str, str]) -> tuple[str, str]:
            if p[0] in {"datetime", "enum", "typing"}:
                return "aaaa" + p[0], p[1]
            return p

        print(f"# generated by flask_typescript on {datetime.now()}", file=out)
        print(
            PREAMBLE.render(
                base=base,
                pyimports=sorted(pyimports, key=key),
                abstract=self.abstract,
            ),
            file=out,
        )
        for model in models:
            print(file=out)
            print(model, file=out)

    def mkcopy(
        self,
        table: Table,
        name: str,
        meta: MetaData,
        pkname: str = "id",
    ) -> Table:
        indexes = table.indexes
        names = {c.key for c in table.c}
        pks = list(table.primary_key.columns)
        cols = [c.copy() for c in table.c if c not in pks]
        pks = [c.copy() for c in pks]
        for pk in pks:
            pk.primary_key = False

        if pkname in names:
            while pkname in names:
                pkname = pkname + "_"

        args: list[Column[Any] | Index] = pks + cols  # type: ignore
        i = Index("fk_index", *(p.name for p in pks), unique=False)
        args.append(i)
        if indexes:
            for i in indexes:
                args.append(
                    Index(i.name, *(c.name for c in i.columns), unique=i.unique),
                )

        return Table(
            name,
            meta,
            Column(pkname, sqla.Integer, primary_key=True),
            *args,
            **table.kwargs,
        )
