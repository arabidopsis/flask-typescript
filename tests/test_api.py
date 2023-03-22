from __future__ import annotations

import unittest

from pydantic import BaseModel
from werkzeug.datastructures import ImmutableMultiDict

from flask_typescript.api import DebugApi


class B(BaseModel):
    b: str


class TestApi(unittest.TestCase):
    def test_Func(self):
        """Test argument passing"""

        class A(BaseModel):
            a: int
            b: str

        def func(a: A, c: B) -> A:
            a.a += 2
            return a

        data = ImmutableMultiDict([("a.a", "1"), ("a.b", "2"), ("c.b", "3")])
        # data = ImmutableMultiDict(flatten({'a':{'a':'1', 'b': '2'}, 'c': {'b':'3'}}))

        api = DebugApi("Debug", data)
        # because A is defined locally
        api.builder.ns = locals()

        ff = api(func)

        result = ff()
        self.assertEqual(result.status_code, 200)
        self.assertEqual(A(**result.json), A(a=3, b="2"))

    def test_Error(self):
        """Test missing argument"""

        class A(BaseModel):
            a: int
            b: str

        def func(a: A, c: B) -> A:
            a.a += 2
            return a

        data = ImmutableMultiDict([("a.a", "1"), ("c.b", "3")])

        api = DebugApi("Debug", data)
        # because A is defined locally
        api.builder.ns = locals()

        ff = api(func)

        result = ff()
        self.assertEqual(result.status_code, 400)
        self.assertTrue(result.is_json)
        self.assertEqual(
            result.json,
            [
                {
                    "loc": ["a", "b"],
                    "msg": "field required",
                    "type": "value_error.missing",
                },
            ],
        )
