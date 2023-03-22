from __future__ import annotations

import unittest
from datetime import date  # noqa: F401

from pydantic import BaseModel
from pydantic import Field

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


def reader(filename: str):
    import pathlib

    p = pathlib.Path(__file__).parent / "resources" / filename
    res: dict[str, str] = {}
    with open(p) as fp:
        typ: list[str] = []
        name = ""
        for line in fp:
            if line.startswith("//>"):
                if typ:
                    e = "".join(typ)
                    res[name] = e[:-1]
                name = line[3:].strip()
                typ = []
            else:
                typ.append(line)
        if typ:
            e = "".join(typ)
            res[name] = e[:-1]
    return res


def get_models():
    return {
        name: v
        for name, v in globals().items()
        if lenient_issubclass(v, BaseModel) and v is not BaseModel
    }


def generate():
    Models = get_models()
    builder = TSBuilder()
    for name, model in Models.items():
        t = builder(model)
        s = t.to_ts()
        print(f"//>{name}")
        print(s)


class TestModels(unittest.TestCase):
    def setUp(self):
        self.Res = reader("tstext.ts")
        self.builder = TSBuilder()
        self.Models = get_models()

    def test_Models(self):
        """Test pydantic model to typescript generation"""
        for name, m in self.Models.items():
            with self.subTest(model=name):
                s, expected = str(self.builder(m)), self.Res[name]
                self.assertEqual(s, expected)


if __name__ == "__main__":
    generate()
