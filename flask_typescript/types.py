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
    type: Literal["success"] = "success"


class Failure(BaseModel):
    errors: list[ErrorDict]
    type: Literal["failure"] = "failure"


class Error(BaseModel):
    status: int
    error: Any
    type: Literal["error"] = "error"


FlaskResult = Success | Failure | Error


MaybeDict: TypeAlias = dict[str, Any] | None
MissingDict: TypeAlias = dict[str, Any] | _MISSING_TYPE
MaybeModel: TypeAlias = BaseModel | _MISSING_TYPE
ModelType = TypeVar("ModelType", bound=BaseModel)

ModelTypeOrMissing: TypeAlias = ModelType | _MISSING_TYPE
JsonDict: TypeAlias = dict[str, Any]
