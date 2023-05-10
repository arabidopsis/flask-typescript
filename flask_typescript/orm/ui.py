from __future__ import annotations

import click
from flask import current_app
from flask.cli import with_appcontext

from ..utils import maybeclose
from .orm import dodatabase
from .orm import find_models
from .orm import model_ts


@click.command()
@with_appcontext
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

    with maybeclose(out) as fp:
        for url in urls:
            dodatabase(url, *tables, preamble=not no_preamble, out=fp)


@click.command()
@with_appcontext
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
