from __future__ import annotations

from typing import Any

from flask_sqlalchemy import SQLAlchemy as _SQLAlchemy
from flask_sqlalchemy.model import Model
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeMeta
from sqlalchemy.orm.decl_api import DeclarativeAttributeIntercept

from .orm import DeclarativeBase
from .orm import is_model


class BindMetaMixin(type):
    __fsa__: SQLAlchemy
    metadata: MetaData

    def __init__(
        cls,
        name: str,
        bases: tuple[type, ...],
        d: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        if not ("metadata" in cls.__dict__):
            bind_key = getattr(cls, "__bind_key__", None)
            parent_metadata = getattr(cls, "metadata", None)
            metadata = cls.__fsa__._make_metadata(bind_key)

            if metadata is not parent_metadata:
                cls.metadata = metadata

        super().__init__(name, bases, d, **kwargs)


class Meta(BindMetaMixin, DeclarativeAttributeIntercept):
    pass


class Base(DeclarativeBase, metaclass=Meta):
    pass


class SQLAlchemy(_SQLAlchemy):
    def __init__(self, **kwargs):
        kwargs.setdefault("model_class", Base)
        super().__init__(**kwargs)

    # def register_metadata(self, namespace):
    #     if "__bind_key__" in namespace and "metadata" not in namespace:
    #         key = namespace.pop("__bind_key__")
    #         namespace["metadata"] = self._make_metadata(key)

    def _make_declarative_base(self, model: type[Model] | DeclarativeMeta) -> type[Any]:
        if not is_model(model):
            return super()._make_declarative_base(model)
        if None not in self.metadatas:
            # Use the model's metadata as the default metadata.
            model.metadata.info["bind_key"] = None  # type: ignore[union-attr]
            self.metadatas[None] = model.metadata  # type: ignore[union-attr]
        else:
            # Use the passed in default metadata as the model's metadata.
            model.metadata = self.metadatas[None]  # type: ignore[union-attr]

        # model.query_class = self.Query
        # model.query = _QueryProperty()
        model.__fsa__ = self
        return model
