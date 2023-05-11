from __future__ import annotations

import click
from flask import current_app
from flask import Flask
from flask.cli import AppGroup

from .api import Api

ts_cli = AppGroup("ts", help="type a flask app")


@ts_cli.command()
@click.option(
    "-o",
    "--out",
    type=click.Path(dir_okay=False),
    help="output file",
)
@click.option(
    "-x",
    "--without-interface",
    is_flag=True,
    help="don't output interface(s)",
)
@click.option(
    "--nosort",
    is_flag=True,
    help="don't sort output of pydantic classes by name",
)
def typescript(
    out: str | None = None,
    without_interface: bool = False,
    nosort: bool = False,
):
    """Generate Typescript types for this Flask app."""
    Api.generate_api(current_app, out, without_interface, nosort)


# @ts_cli.command("formdata")
# @click.option(
#     "-o",
#     "--out",
#     type=click.Path(dir_okay=False),
#     help="output file",
# )
# @click.option(
#     "--nosort",
#     is_flag=True,
#     help="don't sort output of pydantic classes by name",
# )
# def generate_formdata(
#     out: str | None = None,
#     nosort: bool = False,
# ):
#     """Generate Typescript formdata for this Flask app."""
#     Api.generate_form_data(app, out, nosort)


def init_cli(app: Flask):
    try:
        from .orm.ui import tables, models  # noqa: 401
    except ImportError:
        pass

    from .endpoints.ui import endpoints  # noqa: 401

    app.cli.add_command(ts_cli)
