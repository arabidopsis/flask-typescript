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
@click.option("--with-doc", is_flag=True, help="documentations as javascript string")
@click.argument("includes", nargs=-1)
def endpoints(
    includes: list[str],
    out: str | None,
    server: str | None,
    with_doc: bool,
) -> None:
    """Typescript types of Flask endpoints.

    INCLUDES is a list of regular expressions that try to match
    flask route *endpoints*. (See `flask routes`). e.g. to include
    only a particular blueprint use ^blueprint\\\\.
    """

    if server:
        server = server.strip().rstrip("/")

    with maybeclose(out, "wt") as fp:
        endpoints_ts(
            current_app,
            includes=includes,
            out=fp,
            server=server,
            with_doc=with_doc,
        )
