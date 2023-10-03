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
    "-p",
    "--preamble",
    help="import preamble from here",
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
    preamble: str | None = None,
) -> None:
    """Generate Typescript types for this Flask app."""
    Api.generate_api(current_app, out, without_interface, nosort, preamble=preamble)


def dc_to_ts_options(func: Callable[..., Any]) -> Callable[..., Any]:
    func = click.option(
        "-i",
        "--ignore-defaults",
        is_flag=True,
        help="don't output default values",
    )(func)
    func = click.option(
        "--ns",
        help="module name to use as builder namespace",
    )(func)
    func = click.option(
        "--sort",
        is_flag=True,
        help="sort output by type name",
    )(func)
    func = click.option(
        "-o",
        "--out",
        type=click.Path(dir_okay=False),
        help="output file",
    )(func)
    return click.argument("modules", nargs=-1)(func)


@ts_cli.command()
@dc_to_ts_options
def dataclasses(
    out: str | None,
    modules: tuple[str],
    ignore_defaults: bool,
    ns: str | None,
    sort: bool,
) -> None:
    """Generate typescript from dataclass/pydantic models specified in the command line modules"""
    dc_to_ts(out, modules, ignore_defaults, ns, sort)


@ts_cli.command()
def preamble() -> None:
    """print the current preamble"""
    from .utils import get_preamble

    print(get_preamble())


def dc_to_ts(
    out: str | None,
    modules: tuple[str],
    ignore_defaults: bool,
    ns: str | None,
    sort: bool,
) -> None:
    from pathlib import Path
    from importlib import import_module
    from typing import Iterator
    from pydantic import BaseModel
    from .typing import TSBuilder, is_pydantic_type, is_dataclass_type
    from .typing import is_typeddict  # type: ignore[attr-defined]
    from .utils import maybeclose

    def find_py(module: str) -> Iterator[tuple[type[BaseModel], dict[str, Any], bool]]:
        exclude = {BaseModel}
        if "/" in module or module.endswith(".py"):
            pth = Path(module).expanduser()
            g: dict[str, Any] = {}
            with open(pth, encoding="utf-8") as fp:
                exec(fp.read(), g)  # pylint: disable=exec-used
            is_exec = True
        else:
            m = import_module(module)
            if m is None:
                return
            g = m.__dict__
            is_exec = False

        for v in g.values():
            if is_pydantic_type(v) or is_dataclass_type(v) or is_typeddict(v):
                if v in exclude:
                    continue
                yield v, g, is_exec

    namespace = None
    if ns:
        mm = import_module(ns)
        if mm is not None:
            namespace = mm.__dict__
    builder = TSBuilder(ignore_defaults=ignore_defaults, ns=namespace)

    namespace = builder.ns
    mlist = [
        (model, cns, is_exec) for m in modules for model, cns, is_exec in find_py(m)
    ]
    if sort:
        mlist = sorted(mlist, key=lambda t: t[0].__name__)
    with maybeclose(out, "wt") as fp:
        for model, cns, is_exec in mlist:
            if is_exec:
                builder.ns = cns
            print(builder(model), file=fp)
            builder.ns = namespace


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
    # pylint: disable=unused-import
    try:
        from .orm.ui import tables, models, tosqla  # noqa: 401
    except ImportError:
        pass

    from .endpoints.ui import endpoints  # noqa: 401

    app.cli.add_command(ts_cli)
