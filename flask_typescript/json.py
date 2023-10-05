from __future__ import annotations

import decimal
import uuid
from dataclasses import asdict
from dataclasses import is_dataclass
from datetime import date
from typing import Any
from typing import Callable

from flask import Flask
from flask.json.provider import DefaultJSONProvider
from pydantic import BaseModel
from werkzeug.http import http_date


# from flask/json/provider.py
def _default(o: Any) -> Any:
    if isinstance(o, date):
        return http_date(o)

    if isinstance(o, (decimal.Decimal, uuid.UUID)):
        return str(o)

    if is_dataclass(o):
        return asdict(o)

    if hasattr(o, "__html__"):
        return str(o.__html__())

    if isinstance(o, BaseModel):
        return o.model_dump()

    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")


class PydanticJSONProvider(DefaultJSONProvider):
    default: Callable[[Any], Any] = staticmethod(_default)


class PyFlask(Flask):
    """Allow for return types like list[X] where X is a pydantic class"""

    json_provider_class = PydanticJSONProvider
