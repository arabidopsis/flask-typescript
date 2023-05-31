from __future__ import annotations

import re
import sys
from datetime import datetime
from importlib.resources import read_text
from typing import Any
from typing import NamedTuple
from typing import TextIO
from typing import TypedDict

from jinja2 import Template
from sqlalchemy import BINARY
from sqlalchemy import BLOB
from sqlalchemy import CHAR
from sqlalchemy import Column
from sqlalchemy import Date
from sqlalchemy import DateTime
from sqlalchemy import DECIMAL
from sqlalchemy import Enum
from sqlalchemy import Float
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import JSON
from sqlalchemy import MetaData
from sqlalchemy import String
from sqlalchemy import Table
from sqlalchemy import Text
from sqlalchemy import TIMESTAMP
from sqlalchemy.dialects.mysql import DOUBLE
from sqlalchemy.dialects.mysql import LONGBLOB
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.dialects.mysql import MEDIUMBLOB
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.dialects.mysql import SET
from sqlalchemy.dialects.mysql import TEXT
from sqlalchemy.dialects.mysql import TINYTEXT
from sqlalchemy.dialects.mysql import YEAR


PREAMBLE = Template(
    """
{% for mod, name in pyimports %}
from {{mod}} import {{name}}
{%- endfor %}
{% for name in imports %}
from sqlalchemy import {{name}}
{%- endfor %}
{% for mod, name in mysqlimports %}
from {{mod}} import {{name}}
{%- endfor %}
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

{% if not abstract %}
from sqlalchemy.orm import DeclarativeBase

class {{base}}(DeclarativeBase):
    pass
{% endif %}
""",
)


def pascal_case(name: str) -> str:
    name = "".join(n[0].upper() + n[1:] for n in name.split("_"))
    if name.endswith("s"):
        name = name[:-1]
    name = name.replace(".", "_")
    if name in {"Column", "Table", "Integer"}:
        name = name + "Class"
    return name


NAMES = {"class": "class_"}


CNAMES = re.compile("[_ -()/]+")

Number = {
    "1": "one",
    "2": "two",
    "3": "three",
    "4": "four",
    "5": "five",
    "6": "six",
    "7": "seven",
    "8": "eight",
    "9": "nine",
    "0": "zero",
}


def column_name(name: str) -> str:
    cname = CNAMES.sub("_", name)
    cname = NAMES.get(cname, cname)
    if cname[0] in Number:
        cname = Number[cname[0]] + cname[1:]
    return cname


def get_template() -> str:
    return read_text("flask_typescript.orm", "template.py.jinja")


class ColumnInfo(TypedDict):
    name: str
    type: str
    python_type: str
    otype: str
    nullable: bool
    pk: bool
    server_default: str | None
    index: bool | None
    unique: bool
    column_name: str
    max_length: int | None


class TableInfo(TypedDict):
    model: str
    name: str
    columns: list[ColumnInfo]
    charset: str
    indexes: set[Index]
    base: str
    abstract: bool
    with_tablename: bool


class TableData(NamedTuple):
    data: TableInfo
    imports: set[str]
    mysqlimports: set[tuple[str, str]]
    pyimports: set[tuple[str, str]]


def quote(s: str) -> str:
    for q in ['"', "'"]:
        if s.startswith(q) and s.endswith(q):
            return s
    return f'"{s}"'


def clean(s: str) -> str:
    return re.sub(r"\W|^(?=\d)", "_", s)


NS = {"+": "watson", "-": "crick"}


class ModelMaker:
    def __init__(
        self,
        with_tablename: bool = False,
        abstract: bool = False,
        base: str = "Base",
        ns: dict[str, str] | None = NS,
    ):
        self.with_tablename = with_tablename
        self.abstract = abstract
        self.template = Template(get_template())
        self.base = base
        self.ns = ns

    def column_name(self, name: str) -> str:
        return column_name(name)

    def convert_table(  # noqa: C901
        self,
        table: Table,
        enums: dict[frozenset[str], str],
        sets: dict[frozenset[str], str],
    ) -> TableData:
        mysqlimports: set[tuple[str, str]] = set()
        imports: set[str] = set()
        pyimports: set[tuple[str, str]] = set()

        columns: list[ColumnInfo] = []

        indexes = table.indexes
        atyp: str
        charset: str

        do = table.dialect_options.get("mysql")
        if do:
            charset = do["default charset"]
        else:
            charset = ""
        for c in table.columns:
            typ = c.type
            atyp = str(typ)
            pytype = "str"
            server_default = None
            if c.server_default is not None:
                if hasattr(c.server_default, "arg"):
                    # e.g. text("0")
                    server_default = quote(str(c.server_default.arg))
                    server_default = f"text({server_default})"
                    imports.add("text")

            if isinstance(typ, DOUBLE):
                atyp = "DOUBLE"
                pytype = "float"
                imports.add(atyp)
            elif isinstance(typ, Float):
                atyp = "Float"
                pytype = "float"
                imports.add(atyp)
            elif isinstance(typ, Integer):
                atyp = "Integer"
                imports.add(atyp)
                pytype = "int"
            elif isinstance(typ, DECIMAL):
                atyp = f"DECIMAL({typ.precision},{typ.scale})"
                imports.add("DECIMAL")
                pytype = "Decimal"
                pyimports.add(("decimal", "Decimal"))
            elif isinstance(typ, TIMESTAMP):
                atyp = "TIMESTAMP"
                # server_default = 'text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")'
                imports.add(atyp)
                imports.add("text")
                pytype = "datetime"
                pyimports.add(("datetime", "datetime"))
            elif isinstance(typ, DateTime):
                atyp = "DateTime"
                imports.add(atyp)
                pytype = "datetime"
                pyimports.add(("datetime", "datetime"))
            elif isinstance(typ, Date):
                atyp = "Date"
                pytype = "date"
                imports.add(atyp)
                pyimports.add(("datetime", "date"))
            elif isinstance(typ, SET):
                s = frozenset(typ.values)
                if s not in sets:
                    sets[s] = "Set_" + c.name
                atyp = sets[s]
                mysqlimports.add(("sqlalchemy.dialects.mysql", "SET"))
                pytype = "set[str]"
            elif isinstance(typ, Enum):
                s = frozenset(typ.enums)
                if s not in enums:
                    enums[s] = "Enum_" + c.name
                atyp = enums[s]
                imports.add("Enum")
                pyimports.add(("enum", "Enum as PyEnum"))
                pytype = atyp
                atyp = f"Enum({atyp})"
            elif isinstance(typ, (Text, TEXT, MEDIUMTEXT, TINYTEXT, LONGTEXT)):
                name = typ.__class__.__name__
                usecharset = False
                pytype = "str"
                if hasattr(typ, "charset") and typ.charset:
                    if typ.charset != charset:
                        usecharset = True
                        atyp = f'{name}(charset="{typ.charset}")'
                    else:
                        atyp = f"{name}"
                else:
                    if name == "TEXT" and not usecharset:
                        name = "Text"
                    atyp = f"{name}"
                if name.startswith(("TINY", "LONG", "MEDIUM")) or name == "TEXT":
                    mysqlimports.add(("sqlalchemy.dialects.mysql", name))
                else:
                    imports.add(name)

            elif isinstance(typ, (String, CHAR)):
                name = typ.__class__.__name__
                pytype = "str"
                if hasattr(typ, "charset") and typ.charset and typ.charset != charset:
                    atyp = f'{name}({typ.length}, charset="{typ.charset}")'
                    mysqlimports.add(("sqlalchemy.dialects.mysql", name))
                else:
                    if name == "VARCHAR":
                        name = "String"
                    atyp = f"{name}({typ.length})"
                    imports.add(name)
            elif isinstance(typ, (BLOB, LONGBLOB, MEDIUMBLOB)):
                name = typ.__class__.__name__
                atyp = name
                pytype = "bytes"
                mysqlimports.add(("sqlalchemy.dialects.mysql", name))
            elif isinstance(typ, (BINARY,)):
                name = typ.__class__.__name__
                atyp = f"{name}({typ.length})"
                imports.add(name)
            elif isinstance(typ, (JSON)):
                name = typ.__class__.__name__
                atyp = name
                pytype = "Any"
                imports.add(name)
                pyimports.add(("typing", "Any"))
            elif isinstance(typ, YEAR):
                name = typ.__class__.__name__
                atyp = atyp = f"{name}(4)"
                imports.add(name)
                pytype = "int"

            else:
                raise RuntimeError(f'unknown field "{table.name}.{c.name}" {c.type}')
            if c.nullable:
                pytype = f"{pytype} | None"
            d = ColumnInfo(
                name=c.name,
                type=atyp,
                python_type=pytype,
                otype=c.type.__class__.__name__,
                nullable=c.nullable or False,
                pk=c.primary_key,
                server_default=server_default,
                index=c.index,
                unique=c.unique or False,
                column_name=self.column_name(c.name),
                max_length=None,
            )
            if hasattr(c.type, "length"):
                d["max_length"] = c.type.length
            columns.append(d)

            for i in indexes:
                if len(i.columns) == 1:
                    if c.name in i.columns:
                        d["index"] = True
                        d["unique"] = i.unique
                        indexes.remove(i)
                        break
        # for e, name in enums.items():
        #     atyp = "Enum({})".format(", ".join('"%s"' % v for v in e))
        #     elist.append((name, atyp))

        if indexes:
            imports.add("Index")

        data = TableInfo(
            model=self.pascal_case(table.name),
            name=table.name,
            columns=columns,
            charset=charset,
            indexes=indexes,
            base=self.base,
            abstract=self.abstract,
            with_tablename=self.with_tablename,
        )

        return TableData(
            data=data,
            imports=imports,
            mysqlimports=mysqlimports,
            pyimports=pyimports,
        )

    def pascal_case(self, name: str) -> str:
        return pascal_case(name)

    def pyname(self, name: str) -> str:
        name = name.strip()
        if self.ns and name in self.ns:
            return self.ns[name]
        if name.isidentifier():
            return name
        if name[0].isdigit():
            name = Number[name[0]] + name[1:]
        name = clean(name)
        return name

    def run_tables(
        self,
        tables: list[Table],
        out: TextIO = sys.stdout,
    ) -> None:
        mysqlimports: set[tuple[str, str]] = set()
        imports: set[str] = set()
        pyimports: set[tuple[str, str]] = set()
        ret: list[str] = []
        sets: dict[frozenset[str], str] = {}
        enums: dict[frozenset[str], str] = {}
        for table in tables:
            tsets = sets.copy()
            tenums = enums.copy()
            tabledata = self.convert_table(table, enums, sets)
            imports |= tabledata.imports
            mysqlimports |= tabledata.mysqlimports
            pyimports |= tabledata.pyimports
            data = tabledata.data

            xenums = [
                ([(v, self.pyname(v)) for v in k], enums[k])
                for k in set(enums.keys()) - set(tenums.keys())
            ]
            xsets = [
                ([f'"{v}"' for v in k], sets[k])
                for k in set(sets.keys()) - set(tsets.keys())
            ]

            txt = self.render_table(sets=xsets, enums=xenums, **data)

            ret.append(txt)

        self.gen_tables(
            tables,
            ret,
            imports,
            mysqlimports,
            pyimports,
            out=out,
            base=self.base,
        )

    def render_table(self, **data) -> str:
        return self.template.render(**data)

    # pylint: disable=too-many-arguments
    def gen_tables(
        self,
        tables: list[Table],
        models: list[str],
        imports: set[str],
        mysqlimports: set[tuple[str, str]],
        pyimports: set[tuple[str, str]],
        out: TextIO = sys.stdout,
        base: str = "Base",
    ) -> None:
        print(f"# generated by {__file__} on {datetime.now()}", file=out)
        print(
            PREAMBLE.render(
                imports=imports,
                mysqlimports=mysqlimports,
                base=base,
                pyimports=pyimports,
                abstract=self.abstract,
            ),
            file=out,
        )
        for t in models:
            print(file=out)
            print(t, file=out)

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
            Column(pkname, Integer, primary_key=True),
            *args,
            **table.kwargs,
        )
