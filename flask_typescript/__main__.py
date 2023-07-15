from __future__ import annotations

import click

from .cli import dc_to_ts
from .cli import dc_to_ts_options


@click.command()
@dc_to_ts_options
def dataclasses(
    out: str | None,
    modules: tuple[str],
    ignore_defaults: bool,
    ns: str | None,
) -> None:
    """Generate typescript from dataclass/pydantic models specified in the command line modules"""
    dc_to_ts(out, modules, ignore_defaults, ns)


if __name__ == "__main__":
    dataclasses()
