from __future__ import annotations

import unittest
from datetime import date
from datetime import datetime

from pydantic import BaseModel
from werkzeug.datastructures import ImmutableMultiDict
from werkzeug.datastructures import MultiDict

from flask_typescript.debug import DebugApi


class B(BaseModel):
    b: str


class TestApi(unittest.TestCase):
    def test_LocalPydantic(self) -> None:
        """Test NameError in local pydantic definition"""

        class A(BaseModel):
            a: int

        def func(a: A) -> A:
            a.a += 2
            return a

        data: MultiDict = ImmutableMultiDict([("a.a", "1")])

        api = DebugApi("Debug", data)

        with self.assertRaises(NameError):
            _ = api(func)

    def test_Func(self) -> None:
        """Test argument passing"""

        class A(BaseModel):
            a: int
            b: str

        def func(a: A, c: B) -> A:
            self.assertEqual(c.b, "3")
            a.a += 2
            return a

        data: MultiDict = ImmutableMultiDict([("a.a", "1"), ("a.b", "2"), ("c.b", "3")])
        # data = ImmutableMultiDict(flatten({'a':{'a':'1', 'b': '2'}, 'c': {'b':'3'}}))

        api = DebugApi("Debug", data)
        # because A is defined locally
        with api.namespace(locals()):
            ff = api(func)

        result = ff()
        self.assertEqual(result.status_code, 200)
        self.assertEqual(A(**result.json), A(a=3, b="2"))

    def test_Error(self) -> None:
        """Test missing argument"""

        class A(BaseModel):
            a: int
            b: str

        def func(a: A, c: B) -> A:
            a.a += 2
            return a

        data: MultiDict = ImmutableMultiDict([("a.a", "1"), ("c.b", "3")])

        api = DebugApi("Debug", data)
        # because A is defined locally
        with api.namespace(locals()):
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

    def test_JQuery(self) -> None:
        """test jQuery.param encoding"""
        data: MultiDict = ImmutableMultiDict(
            [("a[0]", "1"), ("a[1]", "2"), ("score", "5")],
        )

        class A(BaseModel):
            a: list[int]

        api = DebugApi("Debug", data, decoding="jquery")
        # because A is defined locally

        def func(a: list[int], score: int) -> A:
            a = [v + score for v in a]
            return A(a=a)

        with api.namespace(locals()) as api:
            ff = api(func)

        result = ff()
        self.assertEqual(result.status_code, 200)
        self.assertEqual(A(**result.json), A(a=[1 + 5, 2 + 5]))

    def test_JQuery2(self) -> None:
        """test2 jQuery.param encoding"""
        data: MultiDict = ImmutableMultiDict(
            [("a[0]", "1"), ("a[1]", "2"), ("myb[b]", "xx"), ("score", "5")],
        )

        class A(BaseModel):
            a: list[int]
            myb: B

        api = DebugApi("Debug", data, decoding="jquery")
        # because A is defined locally

        def func(arg: A, score: int) -> A:
            x = [v + score for v in arg.a]
            return A(a=x, myb=arg.myb)

        with api.namespace(locals()) as api:
            ff = api(func)

        result = ff()
        self.assertEqual(result.status_code, 200)
        self.assertEqual(A(**result.json), A(a=[1 + 5, 2 + 5], myb=B(b="xx")))

    def test_Json(self) -> None:
        """test JSON data"""
        data = dict(a=[1, 2], myb=dict(b="xx"), score=5)

        class A(BaseModel):
            a: list[int]
            myb: B

        api = DebugApi("Debug", data, decoding="devalue")
        # because A is defined locally

        def func(arg: A, score: int) -> A:
            x = [v + score for v in arg.a]
            return A(a=x, myb=arg.myb)

        with api.namespace(locals()) as api:
            ff = api(func)

        result = ff()
        self.assertEqual(result.status_code, 200)
        self.assertEqual(A(**result.json), A(a=[1 + 5, 2 + 5], myb=B(b="xx")))

    def test_DateJson(self) -> None:
        """test JSON Date"""

        data = dict(date="2022-01-20", dt="2023-03-20T13:06:38.781Z")
        dt = datetime.fromisoformat(data["dt"])

        class A(BaseModel):
            date: date
            dt: datetime

        api = DebugApi("Debug", data, decoding="devalue")
        # because A is defined locally

        def func(arg: A) -> A:
            return A(date=date.today(), dt=arg.dt)

        with api.namespace(locals()) as api:
            ff = api(func)

        result = ff()
        self.assertEqual(result.status_code, 200)
        self.assertEqual(A(**result.json), A(date=date.today(), dt=dt))

    def test_Result(self) -> None:
        """Test result"""

        class A(BaseModel):
            a: int
            b: str

        def func(a: A, c: B) -> A:
            assert c.b == "3"
            a.a += 2
            return a

        data: MultiDict = ImmutableMultiDict([("a.a", "1"), ("a.b", "2"), ("c.b", "3")])
        # data = ImmutableMultiDict(flatten({'a':{'a':'1', 'b': '2'}, 'c': {'b':'3'}}))

        api = DebugApi("Debug", data, result=True)
        # because A is defined locally

        with api.namespace(locals()) as api:
            ff = api(func)

        result = ff()
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.is_json)
        json = result.json
        self.assertTrue(json.get("type") == "success")
        self.assertEqual(A(**json["result"]), A(a=3, b="2"))

    def test_ResultFail(self) -> None:
        """Test result fail"""
        from flask_typescript.types import Failure

        class A(BaseModel):
            a: int
            b: str

        def func(aa: A, c: B) -> A:
            aa.a += 2
            return aa

        data: MultiDict = ImmutableMultiDict(
            [("aa.a", "s"), ("aa.b", "2"), ("c.b", "3")],
        )

        api = DebugApi("Debug", data, result=True)
        # because A is defined locally
        with api.namespace(locals()) as api:
            ff = api(func)

        result = ff()
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.is_json)
        json = result.json
        self.assertFalse(json.get("type") == "success")
        errors = [
            {
                "loc": ("aa", "a"),
                "msg": "value is not a valid integer",
                "type": "type_error.integer",
            },
        ]
        self.assertEqual(Failure(**json), Failure(error=errors))

    def test_Simple(self) -> None:
        """Test simple argument passing"""

        class A(BaseModel):
            val: float

        def func(a: int, b: float, c: str, d: list[int]) -> A:
            self.assertEqual(c, "err")
            return A(val=a * b + sum(d))

        data: MultiDict = ImmutableMultiDict(
            [
                ("a", "5"),
                ("b", "2.2"),
                ("c", "err"),
                ("d", "3"),
                ("d", "4"),
            ],
        )

        api = DebugApi("Debug", data)
        # because A is defined locally
        with api.namespace(locals()) as api:
            ff = api(func)

        result = ff()
        self.assertEqual(result.status_code, 200)
        self.assertEqual(A(**result.json), A(val=5 * 2.2 + (3 + 4)))
