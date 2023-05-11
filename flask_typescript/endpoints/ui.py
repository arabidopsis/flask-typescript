from __future__ import annotations

import click
from flask import current_app

from ..cli import ts_cli
from ..utils import maybeclose
from .flask_endpoints import endpoints_ts


@ts_cli.command()
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
    """Typescript types of Flask endpoints"""

    if server:
        server = server.rstrip("/")

    with maybeclose(out) as fp:
        endpoints_ts(current_app, out=fp, server=server)
