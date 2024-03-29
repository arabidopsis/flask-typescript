from __future__ import annotations

from datetime import date  # noqa:
from pathlib import Path

from flask import abort
from flask import make_response
from flask import render_template
from flask import Response
from flask import send_file
from pydantic import BaseModel
from pydantic import Field
from werkzeug.datastructures import FileStorage

from .bp import bp
from .orm.models import Attachment
from flask_typescript import Api
from flask_typescript import ApiError
from flask_typescript import PyFlask as Flask

# pylint: disable=redefined-outer-name


class Arg5(BaseModel):
    query: str


class Arg(BaseModel):
    query: str
    selected: list[int]
    doit: bool = False  # unchecked checkboxes are not sent so default to False
    date: date
    val: float = Field(gt=0)  # Annotated[float,pos]
    arg5: Arg5  # name="extra.query"
    checked: list[str] = ["aaa"]

    # @validator('val')
    # def pos_val(cls, v):
    #     if v < 0: raise ValueError('must be positive')
    #     return v


class Arg3(BaseModel):
    selected: list[int]


class Ret1(BaseModel):
    val: list[str]
    res: str


class Json(BaseModel):
    a: int
    b: int


class ArgXX(BaseModel):
    query: str


app = Flask(__name__)

app.config.from_prefixed_env()

api = Api("Base", result=False)


def testwrap(func):
    from functools import wraps

    @wraps(func)
    def myfunc(*args, **kwargs):
        print("checking...")
        return func(*args, **kwargs)

    return myfunc


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/favicon.ico")
def favicon():
    abort(404)


@app.get("/<path>")
def jsstatic(path: str):
    """for javascript module imports e.g. import {x} from './lib'"""
    p = Path(path)
    p = p.parent / "templates" / (p.name + ".js" if not p.name.endswith(".js") else "")
    return send_file(p)


def onexc(e) -> Response:
    ret = api.onexc(e, result=False)
    ret.headers["X-myexc"] = "true"
    return ret


@app.post("/full")
@api
@testwrap
def full(arg: Arg, extra: int = 1) -> Arg:
    # print(request.headers)
    # print(arg, extra)
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
        res=b"---".join(m.read() for m in myfiles).decode("utf-8"),
    )


@app.post("/extra/<int:extra>")
@api
def extra(arg: Arg, extra: int) -> Response:
    # print(arg, extra)
    arg.selected = arg.selected * extra
    return make_response(
        arg.model_dump_json(),
        200,
        {"Content-Type": "application/json"},
    )


@app.post("/arg5")
@api
def arg5(extra: list[ArgXX]) -> Arg5:
    # currently can't create json or FormData to target this
    # since embed will be False

    return Arg5(query=extra[0].query)


@app.get("/arg6")
@api(decoding="jquery")
def arg6(extra: list[ArgXX]) -> Arg5:
    return Arg5(query=extra[0].query)


@app.post("/json")
@api
def json() -> Json:
    return Json(a=1, b=22)


@app.get("/json2")
@api(result=True)
def json2() -> list[dict[str, int]]:
    return [dict(a=1, b=22)]


@app.post("/error")
@api
def error() -> Json:
    """Throw ApiError"""
    raise ApiError(400, payload=dict(message="this has failed"))


@app.get("/save-model")
@api
def save_model(model: Attachment) -> Attachment:
    return model


app.register_blueprint(bp)
# from .orm.models import orm

# from .models2 import Paper, Attachment, Location

# app.extensions["models"] = orm("paper", "attachment", "location")
api.init_app(app)
