from __future__ import annotations

from typing import Any
from typing import TypeGuard

from flask import Response
from werkzeug.datastructures import MultiDict

from .api import Api
from .api import Config
from .api import Decoding
from .api import ExcFunc
from .utils import dedottify
from .utils import jquery_form
from .utils import JsonDict
from .utils import unflatten


def multi(val) -> TypeGuard[MultiDict]:
    return isinstance(val, MultiDict)


class DebugApi(Api):
    """Version of Api that doesn't require a request context. Used only for testing"""

    def __init__(
        self,
        name: str,
        data: MultiDict | dict[str, Any] | str,
        *,
        onexc: ExcFunc | None = None,
        decoding: Decoding = None,
        result: bool = False,
    ):
        super().__init__(
            name,
            onexc=onexc,
            decoding=decoding,
            result=result,
        )
        self.data = data

    def get_req_values(
        self,
        config: Config,
        names: tuple[str, ...],
    ) -> JsonDict:
        decoding = self.config.decoding if config.decoding is None else config.decoding

        data = self.data

        if decoding == "jquery":
            if not multi(data):
                raise TypeError("not a MultiDict for from_jquery")
            data = jquery_form(data)
        elif decoding == "devalue":
            if multi(data):
                raise TypeError("not a json object for as_devalue")
            if isinstance(data, str):
                from .devalue.parse import parse

                data = parse(data)
        else:
            if multi(data):
                data = dedottify(unflatten(data))

        assert isinstance(data, dict)

        return data

    def make_response(self, stuff: str, code: int, headers: dict[str, str]) -> Response:
        return Response(stuff, code, headers)

    @property
    def is_json(self):
        # json tests are just pure dictionaries....
        return not isinstance(self.data, MultiDict)
