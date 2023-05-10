from __future__ import annotations

import click
from flask.cli import with_appcontext

from .flask_endpoints import get_endpoints


@click.command()
@with_appcontext
@click.option(
    "-o",
    "--out",
    type=click.Path(dir_okay=False),
    help="output file",
)
@click.argument("modules", nargs=-1)
def endpoints(modules: tuple[str], out: str | None):
    """Typescript types from sqlalchemy Models"""
    from flask import current_app

    for ep in get_endpoints(current_app, ["bp"], static=False):
        print(ep.endpoint, ep.methods, ep.url_arguments, ep.url, ep.url_fmt_arguments)

        print(ep.to_ts())
