from __future__ import annotations

import click

from .cli import dc_to_ts
from .cli import dc_to_ts_options


@click.group()
@click.version_option()
def ts() -> None:
    pass


@ts.command()
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


if __name__ == "__main__":
    ts()
