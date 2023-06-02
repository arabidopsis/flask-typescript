from __future__ import annotations

import click
from flask import current_app

from ..cli import ts_cli
from ..utils import maybeclose
from .orm import dodatabase
from .orm import find_models
from .orm import model_ts


def geturl(url: str | None) -> list[str]:
    if not url:
        url = current_app.config.get("SQLALCHEMY_DATABASE_URI")
        if url is None:
            binds = current_app.config.get("SQLALCHEMY_BINDS")
            if binds is None:
                raise click.BadParameter("no SQLALCHEMY_DATABASE_URI configured")
            urls = [str(u) for u in binds.values()]
        else:
            urls = [str(url)]
    else:
        urls = [url]
    return urls


@ts_cli.command()
@click.option(
    "-o",
    "--out",
    type=click.Path(dir_okay=False),
    help="output file",
)
@click.option(
    "--url",
    help="sqlalchemy connection url to use",
)
@click.option(
    "--no-preamble",
    is_flag=True,
    help="don't output preamble",
)
@click.argument("tables", nargs=-1)
def tables(
    url: str | None,
    tables: tuple[str],
    out: str | None,
    no_preamble: bool = False,
) -> None:
    """Typescript metadata from tables in flask_sqlalchemy"""
    urls = geturl(url)
    with maybeclose(out) as fp:
        for url in urls:
            dodatabase(url, *tables, preamble=not no_preamble, out=fp)


@ts_cli.command()
@click.option(
    "-o",
    "--out",
    type=click.Path(dir_okay=False),
    help="output file",
)
@click.argument("modules", nargs=-1)
def models(modules: tuple[str], out: str | None):
    """Typescript types from sqlalchemy Models"""
    from flask import current_app

    with maybeclose(out) as fp:
        print("// generated by flask-typescript", file=fp)
        if not modules:
            Models = current_app.extensions.get("models")
            if Models is None:
                return
            model_ts(*Models, out=fp)

        else:
            for mod in modules:
                Models = list(find_models(mod))
                if not Models:
                    continue
                print(f"// {mod}")
                model_ts(*Models, out=fp)


@ts_cli.command()
@click.option(
    "-o",
    "--out",
    type=click.Path(dir_okay=False),
    help="output file",
)
@click.option(
    "--url",
    help="sqlalchemy connection url to use",
)
@click.option("--base", default="Base", help="base class of models")
@click.option("--schema", help="schema to use")
@click.option(
    "--throw",
    is_flag=True,
    help="throw on unknown column type (instead of just guessing)",
)
@click.option("--abstract", is_flag=True, help="make classes abstract")
@click.argument("tables", nargs=-1)
def tosqla(
    url: str | None,
    base: str,
    out: str | None,
    abstract: bool,
    schema: str | None,
    tables: tuple[str],
    throw: bool,
):
    """Render tables into sqlalchemy.ext.declarative classes."""

    from sqlalchemy import create_engine, MetaData, Table
    from .mksqla import ModelMaker

    urls = geturl(url)
    ttables: list[Table] = []
    uout = []
    for url in urls:
        engine = create_engine(url)
        uout.append(str(engine.url))  # hide password
        meta = MetaData()
        if tables:
            meta.reflect(bind=engine, only=tables, schema=schema)
        else:
            meta.reflect(bind=engine, schema=schema)
            tables = meta.tables.keys()

        ttables.extend([meta.tables[t] for t in sorted(tables)])
    mm = ModelMaker(
        with_tablename=not abstract,
        abstract=abstract,
        base=base,
        throw=throw,
    )
    with maybeclose(out) as fp:
        print(f'# from {", ".join(uout)}', file=fp)
        mm(ttables, out=fp)
