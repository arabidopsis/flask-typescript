from __future__ import annotations

from dataclasses import _MISSING_TYPE
from typing import Any
from typing import Generic
from typing import Literal
from typing import TypeAlias
from typing import TypeVar

from pydantic import BaseModel
from typing_extensions import TypedDict

# from pydantic_core import ErrorDetails

Loc = list[int | str]


T = TypeVar("T")


class Success(BaseModel, Generic[T]):
    result: T
    type: Literal["success"] = "success"


# HACK! can't just use ErrorDetails from pydantic_core! unless python >= 3.12
class ErrorDetails(TypedDict):
    type: str
    """
    The type of error that occurred, this is an identifier designed for
    programmatic use that will change rarely or never.

    `type` is unique for each error message, and can hence be used as an identifier to build custom error messages.
    """
    loc: tuple[int | str, ...]
    """Tuple of strings and ints identifying where in the schema the error occurred."""
    msg: str
    """A human readable error message."""
    # input: Any
    # """The input data at this `loc` that caused the error."""
    # ctx: dict[str, Any]


class Failure(BaseModel):
    errors: list[ErrorDetails]  # | list[PyErrorDict]
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
