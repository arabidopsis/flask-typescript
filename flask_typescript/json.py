from __future__ import annotations

import dataclasses
import decimal
import uuid
from datetime import date
from typing import Any
from typing import Callable

from flask import Flask
from flask.json.provider import DefaultJSONProvider as FlaskDefaultJSONProvider
from pydantic import BaseModel
from werkzeug.http import http_date


# from flask/json/provider.py
def _default(o: Any) -> Any:
    if isinstance(o, date):
        return http_date(o)

    if isinstance(o, (decimal.Decimal, uuid.UUID)):
        return str(o)

    if dataclasses and dataclasses.is_dataclass(o):
        return dataclasses.asdict(o)

    if hasattr(o, "__html__"):
        return str(o.__html__())

    if isinstance(o, BaseModel):
        return o.dict()

    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")


class DefaultJSONProvider(FlaskDefaultJSONProvider):
    default: Callable[[Any], Any] = staticmethod(_default)


class PyFlask(Flask):
    """Allow for return types like list[X] where X is a pydantic class"""

    json_provider_class = DefaultJSONProvider
