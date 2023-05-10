from __future__ import annotations

import inspect
import re
from collections import defaultdict
from dataclasses import dataclass
from dataclasses import replace
from typing import Any
from typing import Iterator
from typing import Sequence

from flask import current_app
from flask import Flask
from werkzeug.routing import parse_converter_args
from werkzeug.routing import Rule


_rule_re = re.compile(
    r"""
    (?P<static>[^<]*)                           # static rule data
    <
    (?:
        (?P<converter>[a-zA-Z_][a-zA-Z0-9_]*)   # converter name
        (?:\((?P<args>.*?)\))?                  # converter arguments
        \:                                      # variable delimiter
    )?
    (?P<variable>[a-zA-Z_][a-zA-Z0-9_]*)        # variable name
    >
    """,
    re.VERBOSE,
)


def parse_rule(rule: str) -> Iterator[tuple[str | None, str | None, str]]:
    """Parse a rule and return it as generator. Each iteration yields tuples
    in the form ``(converter, arguments, variable)``. If the converter is
    `None` it's a static url part, otherwise it's a dynamic one.

    :internal:
    """
    pos = 0
    end = len(rule)
    do_match = _rule_re.match
    used_names = set()
    while pos < end:
        m = do_match(rule, pos)
        if m is None:
            break
        data = m.groupdict()
        if data["static"]:
            yield None, None, data["static"]
        variable = data["variable"]
        converter = data["converter"] or "default"
        if variable in used_names:
            raise ValueError(f"variable name {variable!r} used twice.")
        used_names.add(variable)
        yield converter, data["args"] or None, variable
        pos = m.end()
    if pos < end:
        remaining = rule[pos:]
        if ">" in remaining or "<" in remaining:
            raise ValueError(f"malformed url rule: {rule!r}")
        yield None, None, remaining


@dataclass
class Fmt:
    converter: str | None
    args: tuple[tuple[str, ...], dict[str, Any]] | None  # args and kwargs
    variable: str

    @property
    def is_static(self):
        return self.converter is None

    @property
    def ts_type(self):
        if self.args and self.converter == "any":
            return " | ".join(repr(s) for s in self.args[0])
        return {
            "default": "string",
            "int": "number",
            "float": "number",
            "any": "string",
            "path": "string",
        }.get(self.converter, self.converter)


@dataclass
class ApiFunction:
    endpoint: str
    methods: list[str]
    method: str
    doc: str | None
    rule: str
    url_fmt_arguments: list[Fmt]
    url: str
    url_arguments: list[str]
    defaults: dict[str, Any]

    def resolve_defaults(self, app: Flask | None = None) -> ApiFunction:
        values: dict[str, Any] = {}
        (app or current_app).inject_url_defaults(self.endpoint, values)
        if not values:
            return self

        v = {}
        url_arguments = list(self.url_arguments)
        for a in self.url_arguments:
            if a in values:
                v[a] = values[a]
                url_arguments.remove(a)
            else:
                v[a] = "${%s}" % a
        url = "".join(
            f.variable if f.is_static else "{%s}" % f.variable
            for f in self.url_fmt_arguments
        )
        url = url.format(**v)

        return replace(self, url=url, url_arguments=url_arguments)

    def find_type(self, variable: str) -> str | None:
        for fmt in self.url_fmt_arguments:
            if fmt.variable == variable:
                return fmt.ts_type
        return None

    def to_ts(self) -> str:
        method = str(self.methods)
        m1 = f"method: {method}"
        args = ", ".join(
            f"{fmt.variable}: {fmt.ts_type}"
            for fmt in self.url_fmt_arguments
            if not fmt.is_static
        )
        url = f"url({args}) {{ return `{self.url}`}}"
        return ",\n".join([m1, url])


def sanitize_doc(s: str | None) -> str | None:
    if s is None:
        return None
    s = re.sub(r"\s*[\r\n]+\s*", "\n" + (" " * 8), s) if s is not None else ""
    return s.strip()


class JavascriptAPI:
    def __init__(
        self,
        endpoints: str | Sequence[str] | None = None,
        *,
        default_as_get: bool = False,
        inject_url_defaults: bool = False,
        static: bool = False,
    ):
        if endpoints is None:
            endpoints = []
        elif isinstance(endpoints, str):
            endpoints = [endpoints]
        self.endpoints = endpoints

        self.default_as_get = default_as_get
        self.static = static
        self.inject_url_defaults = inject_url_defaults

    def get_endpoints(self, app: Flask) -> list[ApiFunction]:
        ret: list[ApiFunction] = []
        # capture defaults first!
        defaults: dict[str, dict[str, Any]] = defaultdict(dict)
        for r in app.url_map.iter_rules():
            if r.defaults:
                defaults[r.endpoint].update(r.defaults)
        for r in sorted(app.url_map.iter_rules(), key=lambda r: r.endpoint):
            if not r.methods or ("GET" not in r.methods and "POST" not in r.methods):
                continue
            endpoint, func_name = (
                r.endpoint.split(".", 1) if "." in r.endpoint else (r.endpoint, "main")
            )  # noqa:

            if self.endpoints and endpoint not in self.endpoints:
                continue
            if not self.static and "static" in r.endpoint:  # skip static
                continue
            api = self.process_rule(
                r,
                app,
                defaults=defaults[r.endpoint],
            )
            if api is None:
                continue
            if set(api.url_arguments) < set(list(r.arguments)):
                # skip default urls
                continue
            if self.inject_url_defaults:
                api = api.resolve_defaults(app)

            ret.append(api)
        return ret

    def process_rule(
        self,
        r: Rule,
        app: Flask,
        *,
        defaults: dict[str, Any] | None = None,
    ) -> ApiFunction | None:
        view_func = app.view_functions[r.endpoint]
        if view_func is None:
            return None
        if r.methods is None:
            return None
        if defaults is None:
            defaults = {}

        doc = inspect.getdoc(view_func)
        # doc = sanitize_doc(view_func.__doc__)

        method = (
            "GET"
            if self.default_as_get and "GET" in r.methods
            else (
                "POST"
                if "POST" in r.methods
                else ("GET" if "GET" in r.methods else None)
            )
        )  # noqa:
        if method is None:
            return None

        # u[0] is the converter and u[1] is its arguments if any
        # u[0] is None for "static" and 'default' for string
        # u[2] is variable name

        url_fmt_arguments = [
            Fmt(u[0], parse_converter_args(u[1]) if u[1] is not None else None, u[2])
            for u in parse_rule(r.rule)
        ]
        # format javascript url template string
        url = "".join(
            f.variable if f.is_static else "${%s}" % f.variable
            for f in url_fmt_arguments
        )
        url_arguments = [f.variable for f in url_fmt_arguments if not f.is_static]

        # create a unique argument name for data arg
        data_name = "data"
        while data_name in url_arguments:
            data_name += "_"
        api = ApiFunction(
            endpoint=r.endpoint,
            methods=sorted(filter(lambda n: n in {"GET", "POST"}, r.methods)),
            method=method,
            doc=doc,
            rule=r.rule,
            url=url,
            url_fmt_arguments=url_fmt_arguments,
            url_arguments=url_arguments,
            defaults=defaults,
        )

        return api


def get_endpoints(
    app: Flask,
    endpoint: str | Sequence[str] | None = None,
    default_as_get: bool = False,
    static: bool = False,
    inject_url_defaults: bool = False,
) -> list[ApiFunction]:
    return JavascriptAPI(
        endpoint,
        default_as_get=default_as_get,
        inject_url_defaults=inject_url_defaults,
        static=static,
    ).get_endpoints(app)
