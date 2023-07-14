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
@click.argument("includes", nargs=-1)
def endpoints(includes: list[str], out: str | None, server: str | None) -> None:
    """Typescript types of Flask endpoints"""

    if server:
        server = server.strip().rstrip("/")

    with maybeclose(out, "wt") as fp:
        endpoints_ts(current_app, includes=includes, out=fp, server=server)
