from __future__ import annotations

import unittest
from datetime import date  # noqa: F401
from typing import Annotated
from typing import Generic
from typing import TypeVar

from pydantic import BaseModel
from pydantic import Field
from pydantic.generics import GenericModel

from flask_typescript.typing import TSBuilder
from flask_typescript.utils import lenient_issubclass


class Y(BaseModel):
    y: int


class Z(BaseModel):
    z: int


class X(BaseModel):
    val: int = 5
    val2: str
    my: tuple[Y, Z]
    my2: Y | Z = Y(y=1)


class Arg(BaseModel):
    query: str
    selected: list[int]
    doit: bool = False  # unchecked checkboxes are not sent so default to False
    date: date
    val: float = Field(gt=0)  # Annotated[float,pos]
    arg5: Z  #
    checked: list[str] = ["aaa"]


class WithAnnotated(BaseModel):
    query: Annotated[float, lambda x: x > 0]


T = TypeVar("T", int, str)


class GenericPY(GenericModel, Generic[T]):
    value: T
    values: list[T]


class GenericList(GenericModel, Generic[T]):
    value: list[T]


class LinkedList(BaseModel):
    a: int = 123
    b: LinkedList | None = None


class GenericTuple(GenericModel, Generic[T]):
    value: tuple[T, int]


GenericFunc_expected = "export type GenericFunc<T= number | string> = (a: T, b: T) => T"


def GenericFunc(a: T, b: T) -> T:
    return a + b


KEY = "//>"


def model_reader(filename: str) -> dict[str, str]:
    import pathlib

    p = pathlib.Path(__file__).parent / "resources" / filename
    res: dict[str, str] = {}
    with open(p) as fp:
        typ: list[str] = []
        name = ""
        for line in fp:
            if line.startswith(KEY):
                if typ:
                    e = "".join(typ)
                    res[name] = e.rstrip()
                name = line[len(KEY) :].strip()
                typ = []
            else:
                typ.append(line)
        if typ:
            e = "".join(typ)
            res[name] = e.rstrip()
    return res


def get_models():
    return {
        name: v
        for name, v in globals().items()
        if lenient_issubclass(v, BaseModel)
        and v is not BaseModel
        and v is not GenericModel
    }


def generate():
    Models = get_models()
    builder = TSBuilder()
    for name, model in Models.items():
        t = builder(model)
        s = t.to_ts()
        print(f"{KEY}{name}")
        print(s)


class TestModels(unittest.TestCase):
    def setUp(self):
        self.Res = model_reader("tstext.ts")
        self.builder = TSBuilder()
        self.Models = get_models()

    def test_Models(self):
        """Test pydantic model to typescript generation"""
        for name, m in self.Models.items():
            with self.subTest(model=name):
                s, expected = str(self.builder(m)), self.Res[name]
                self.assertEqual(s, expected)

    def test_GenericFunc(self):
        """Test generic function"""
        val = str(self.builder(GenericFunc))

        self.assertEqual(val, GenericFunc_expected)


if __name__ == "__main__":
    generate()
