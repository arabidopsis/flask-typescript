from __future__ import annotations

from dataclasses import _MISSING_TYPE
from typing import Any
from typing import Generic
from typing import Literal
from typing import TypeAlias
from typing import TypedDict
from typing import TypeVar

from pydantic import BaseModel
from pydantic.generics import GenericModel


Loc = tuple[int | str, ...]


class ErrorDict(TypedDict):
    loc: Loc
    msg: str
    type: str


T = TypeVar("T")


class Success(GenericModel, Generic[T]):
    result: T
    success: Literal[True] = True


class Error(BaseModel):
    error: list[ErrorDict]
    success: Literal[False] = False


Result = Success | Error


MaybeDict: TypeAlias = dict[str, Any] | None
MissingDict: TypeAlias = dict[str, Any] | _MISSING_TYPE
MaybeModel: TypeAlias = BaseModel | _MISSING_TYPE
ModelType = TypeVar("ModelType", bound=BaseModel)

JsonDict: TypeAlias = dict[str, Any]
