from __future__ import annotations

from datetime import date  # noqa:

from flask import Flask
from flask import make_response
from flask import render_template
from flask import request
from flask import Response
from pydantic import BaseModel
from pydantic import Field
from werkzeug.datastructures import FileStorage

from flask_typescript.api import Api


class Arg5(BaseModel):
    query: str


class Arg(BaseModel):
    query: str
    selected: list[int]
    doit: bool = False  # unchecked checkboxes are not sent so default to False
    date: date
    val: float
    extra: Arg5  # name="extra.query"
    checked: list[str] = Field(default_factory=lambda: ["a"])


class Arg3(BaseModel):
    selected: list[int]


class Ret1(BaseModel):
    val: list[str]
    res: str


class Json(BaseModel):
    a: int
    b: int


app = Flask(__name__)

api = Api("Base")


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/full")
@api
def full(arg: Arg, extra: int = 1) -> Arg:
    print(request.headers)
    print(arg, extra)
    arg.selected = arg.selected * extra
    arg.date = arg.date.today()
    return arg


@app.get("/qqq")
@api
def qqq(a: int, b: int = 5) -> Arg5:
    return Arg5(query=f"{a}-{b}")


@app.post("/filestorage")
@api
def filestorage(val: list[int], myfiles: list[FileStorage]) -> Ret1:
    for f in myfiles:
        print(f.filename, f.content_length, f.content_type)
    return Ret1(
        val=[str(v * 4) for v in val],
        res=b"---".join(m.read() for m in myfiles),
    )


@app.get("/extra/<int:extra>")
@api
def extra(arg: Arg, extra: int) -> Response:
    print(arg, extra)
    arg.selected = arg.selected * extra
    return make_response(arg.json(), 200, {"Content-Type": "application/json"})


@app.post("/json")
@api
def json() -> Json:
    return Json(a=1, b=22)


api.init_app(app)
