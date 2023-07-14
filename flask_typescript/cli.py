from __future__ import annotations

from typing import Any
from typing import Callable
from typing import overload

import click
from click import Command
from flask import current_app
from flask import Flask
from flask.cli import AppGroup

from .api import Api


class TAppGroup(AppGroup):
    @overload
    def command(self, __func: Callable[..., Any]) -> Command:
        ...

    @overload
    def command(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> Callable[[Callable[..., Any]], Command]:
        ...

    def command(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> Callable[[Callable[..., Any]], Command] | Command:
        return super().command(*args, *kwargs)  # type: ignore[no-untyped-call, no-any-return]


ts_cli = TAppGroup("ts", help="type a flask app")


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
) -> None:
    """Generate Typescript types for this Flask app."""
    Api.generate_api(current_app, out, without_interface, nosort)


@ts_cli.command()
@click.option(
    "-i",
    "--ignore-defaults",
    is_flag=True,
    help="don't output default values",
)
@click.option(
    "-o",
    "--out",
    type=click.Path(dir_okay=False),
    help="output file",
)
@click.option(
    "--ns",
    help="builder namespace",
)
@click.argument("modules", nargs=-1)
def dataclasses(
    out: str | None,
    modules: tuple[str],
    ignore_defaults: bool,
    ns: str | None,
) -> None:
    """Generate typescript from dataclass/pydantic models specified in the command line modules"""
    from importlib import import_module
    from typing import Iterator
    from pydantic import BaseModel
    from pydantic.generics import GenericModel
    from .typing import TSBuilder, is_pydantic_type, is_dataclass_type
    from .utils import maybeclose

    def find_py(module: str) -> Iterator[BaseModel]:
        exclude = {BaseModel, GenericModel}

        m = import_module(module)
        if m is None:
            return
        for v in m.__dict__.values():
            if is_pydantic_type(v) or is_dataclass_type(v):
                if v in exclude:
                    continue
                yield v

    namespace = None
    if ns:
        mm = import_module(ns)
        if mm is not None:
            namespace = mm.__dict__
    builder = TSBuilder(ignore_defaults=ignore_defaults, ns=namespace)
    with maybeclose(out, "wt") as fp:
        for m in modules:
            for model in find_py(m):
                print(builder(model), file=fp)  # type: ignore


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


def init_cli(app: Flask) -> None:
    try:
        from .orm.ui import tables, models, tosqla  # noqa: 401
    except ImportError:
        pass

    from .endpoints.ui import endpoints  # noqa: 401

    app.cli.add_command(ts_cli)
