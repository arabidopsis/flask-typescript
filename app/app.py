from __future__ import annotations

from flask import Flask
from flask import jsonify
from flask import render_template
from pydantic import BaseModel
from pydantic import Field

from flask_typescript.api import Api


class Arg(BaseModel):
    query: str
    selected: list[int]
    doit: bool = False
    checked: list[str] = Field(default_factory=lambda: ["aa"])


class Arg2(BaseModel):
    arg: list[Arg]
    stuff: str = "aa"


app = Flask(__name__)

api = Api()


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/bb")
@api
def bbb(arg2: Arg2, extra: int = 1) -> Arg:
    return arg2.arg[0]


@app.post("/aa")
@api
def aaa(arg: Arg, extra: int = 1) -> Arg:
    print(arg, extra)
    arg.selected = arg.selected * extra
    return arg


@app.get("/my/<int:extra>")
@api
def extra(arg: Arg, extra: int):
    print(arg, extra)
    arg.selected = arg.selected * extra
    return arg.json(), 200, {"Content-Type": "application/json"}


@app.get("/my2/<int:extra>")
def extra2(extra: int):
    print(extra)
    return jsonify(dict(extra=extra))


@app.post("/json")
def json():
    return jsonify({"a": 1, "b": 2})


api.init_app(app)
