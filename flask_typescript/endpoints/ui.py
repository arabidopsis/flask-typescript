from __future__ import annotations

import click
from flask import current_app
from flask.cli import with_appcontext

from ..utils import maybeclose
from .flask_endpoints import endpoints_ts


@click.command()
@with_appcontext
@click.option(
    "-o",
    "--out",
    type=click.Path(dir_okay=False),
    help="output file",
)
@click.option(
    "--server",
    help="server to connect to",
)
def endpoints(out: str | None, server: str | None):
    """Typescript types from sqlalchemy Models"""

    if server:
        server = server.rstrip("/")

    with maybeclose(out) as fp:
        endpoints_ts(current_app, out=fp, server=server)
