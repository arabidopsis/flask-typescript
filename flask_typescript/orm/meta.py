from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from typing import get_type_hints

import pydantic
from sqlalchemy import inspect
from sqlalchemy.exc import NoInspectionAvailable
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import MappedAsDataclass
from sqlalchemy.orm import RelationshipProperty
from sqlalchemy.orm.decl_api import DCTransformDeclarative
from sqlalchemy.orm.decl_api import DeclarativeAttributeIntercept

# Registry: dict[str | None, MetaData] = {}


# def register_metadata(namespace: dict[str, Any]) -> None:
#     if "__bind_key__" in namespace and "metadata" not in namespace:
#         key = namespace.pop("__bind_key__")
#         # namespace['metadata'] = SQLAlchemy()._make_metadata(key)
#         # return
#         if key is None:
#             if key not in Registry:
#                 m = DCBase.metadata
#                 if "bind_key" not in m.info:
#                     m.info["bind_key"] = None
#                 Registry[None] = m

#             return
#         if key not in Registry:
#             Registry[key] = MetaData(info=dict(bind_key=key))

#         namespace["metadata"] = Registry[key]


class DCMeta(DCTransformDeclarative):
    def __new__(
        mcs,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kw: Any,
    ) -> Any:
        name = namespace.pop("__clsname__", name)
        return super().__new__(mcs, name, bases, namespace, **kw)


class Meta(DeclarativeAttributeIntercept):
    def __new__(
        mcs,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kw: Any,
    ) -> Any:
        name = namespace.pop("__clsname__", name)
        return super().__new__(mcs, name, bases, namespace, **kw)


class _DCBase(DeclarativeBase):
    __clsname__: str


class DCBase(
    MappedAsDataclass,
    _DCBase,
    metaclass=DCMeta,
    dataclass_callable=dataclass,
):
    """Base class for dataclass ORMs that understands __clsname__ for dynamic construction"""

    __abstract__ = True


class PYBase(
    MappedAsDataclass,
    _DCBase,
    metaclass=DCMeta,
    dataclass_callable=pydantic.dataclasses.dataclass,
):
    """Base class for *pydantic* ORMs that understands __clsname__ for dynamic construction"""

    __abstract__ = True


class Base(_DCBase, metaclass=Meta):
    """Base class that understands __clsname__ for dynamic construction"""

    __abstract__ = True


def get_type_hints_sqla(
    Cls: type[DeclarativeBase],
    globalns: dict[str, Any] | None = None,
    localns: dict[str, Any] | None = None,
    include_extras: bool = False,
) -> dict[str, Any]:
    """add missing relationship values to type hints with @declared_attr"""
    # Mapped[int] really just has m.__args__ == (int,) and m.__origin__ == Mapped

    def getargument(r: RelationshipProperty[Any]) -> Any:
        if isinstance(r.argument, type) and issubclass(r.argument, DeclarativeBase):
            return r.argument
        if callable(r.argument):
            return r.argument()
        return r.argument

    def totype(r: RelationshipProperty[Any]) -> type[Mapped[type]]:
        cls = getargument(r)
        if r.uselist:
            cls = list[cls]  # type: ignore[valid-type]
        return Mapped[cls]  # type: ignore[valid-type]

    try:
        relationships = inspect(Cls).relationships  # type: ignore
    except NoInspectionAvailable:  # a raw DeclarativeBase?
        relationships = []

    th = get_type_hints(
        Cls,
        globalns=globalns,
        localns=localns,
        include_extras=include_extras,
    )

    d = {r.key: totype(r) for r in relationships if r.key not in th}
    if d:
        th.update(d)
    if "__clsname__" in th:
        del th["__clsname__"]
    return th
