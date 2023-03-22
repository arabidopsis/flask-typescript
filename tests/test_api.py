from __future__ import annotations

import unittest
from datetime import date  # noqa:

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

    def test_JQuery(self):
        """test jQuery.param encoding"""
        data = ImmutableMultiDict([("a[0]", "1"), ("a[1]", "2"), ("score", "5")])

        class A(BaseModel):
            a: list[int]

        api = DebugApi("Debug", data, from_jquery=True)
        # because A is defined locally
        api.builder.ns = locals()

        def func(a: list[int], score: int) -> A:
            a = [v + score for v in a]
            return A(a=a)

        ff = api(func)

        result = ff()
        self.assertEqual(result.status_code, 200)
        self.assertEqual(A(**result.json), A(a=[1 + 5, 2 + 5]))

    def test_JQuery2(self):
        """test2 jQuery.param encoding"""
        data = ImmutableMultiDict(
            [("a[0]", "1"), ("a[1]", "2"), ("myb[b]", "xx"), ("score", "5")],
        )

        class A(BaseModel):
            a: list[int]
            myb: B

        api = DebugApi("Debug", data, from_jquery=True)
        # because A is defined locally
        api.builder.ns = locals()

        def func(arg: A, score: int) -> A:
            x = [v + score for v in arg.a]
            return A(a=x, myb=arg.myb)

        ff = api(func)

        result = ff()
        self.assertEqual(result.status_code, 200)
        self.assertEqual(A(**result.json), A(a=[1 + 5, 2 + 5], myb=B(b="xx")))

    def test_Json(self):
        """test JSON"""
        data = dict(a=[1, 2], myb=dict(b="xx"), score=5)

        class A(BaseModel):
            a: list[int]
            myb: B

        api = DebugApi("Debug", data, as_devalue=True)
        # because A is defined locally
        api.builder.ns = locals()

        def func(arg: A, score: int) -> A:
            x = [v + score for v in arg.a]
            return A(a=x, myb=arg.myb)

        ff = api(func)

        result = ff()
        self.assertEqual(result.status_code, 200)
        self.assertEqual(A(**result.json), A(a=[1 + 5, 2 + 5], myb=B(b="xx")))

    def test_JsonDate(self):
        """test JSON Date"""

        data = dict(date="2022-01-20")

        class A(BaseModel):
            date: date

        api = DebugApi("Debug", data, as_devalue=True)
        # because A is defined locally
        api.builder.ns = locals()

        def func(arg: A) -> A:
            return A(date=date.today())

        ff = api(func)

        result = ff()
        self.assertEqual(result.status_code, 200)
        self.assertEqual(A(**result.json), A(date=date.today()))
