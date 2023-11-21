from __future__ import annotations

from dataclasses import MISSING
from typing import Any
from typing import cast

from ..utils import lenient_issubclass

# pylint: disable=unused-argument
try:
    from sqlalchemy.orm import DeclarativeBase
    from sqlalchemy.orm import MappedColumn
    from sqlalchemy.sql.base import NO_ARG

    def is_mapped_column(obj: Any) -> bool:
        return isinstance(obj, MappedColumn)

    def is_declarative(obj: Any) -> bool:
        return lenient_issubclass(obj, DeclarativeBase)

    def find_mapped_default(obj: Any) -> Any:
        a = cast(MappedColumn[Any], obj)
        ao = a._attribute_options  # pylint: disable=protected-access

        if ao.dataclasses_init is False:
            return None
        ret = ao.dataclasses_default_factory
        if ret != NO_ARG:
            return ret()  # type: ignore

        v = ao.dataclasses_default
        if v == NO_ARG:
            v = MISSING
        return v

except ImportError:

    def is_mapped_column(obj: Any) -> bool:
        return False

    def is_declarative(obj: Any) -> bool:
        return False

    def find_mapped_default(obj: Any) -> Any:
        return MISSING
