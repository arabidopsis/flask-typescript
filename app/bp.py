from __future__ import annotations

from flask import Blueprint


bp = Blueprint("bp", __name__)


@bp.route("/very/<int:silly>")
def silly(silly: int):
    return "OK"


@bp.route("/<project>/very/<any(a, b, c):silly>")
def silly2(project: str, silly: str):
    return "OK"


@bp.route("/very/<float:silly>")
def silly3(silly: float):
    return "OK"


@bp.route("/very/<path:silly>")
def silly4(silly: str):
    return "OK"
