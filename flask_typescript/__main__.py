# pylint: disable=unused-import
from __future__ import annotations

from . import typing  # noqa:
from .cli import cli

if __name__ == "__main__":
    cli.main(prog_name="flask-typescript")
