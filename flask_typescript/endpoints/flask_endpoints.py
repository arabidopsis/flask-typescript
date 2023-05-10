from __future__ import annotations

import inspect
import re
from collections import defaultdict
from dataclasses import dataclass
from dataclasses import replace
from typing import Any
from typing import Iterator
from typing import Literal
from typing import Sequence
from typing import TextIO

from flask import current_app
from flask import Flask
from werkzeug.routing import parse_converter_args
from werkzeug.routing import Rule

from ..typing import INDENT
from ..typing import NL

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
class Endpoint:
    endpoint: str
    methods: list[Literal["GET", "POST"]]
    doc: str | None
    rule: str
    url_fmt_arguments: list[Fmt]
    url: str
    url_arguments: list[str]
    defaults: dict[str, Any]
    server: str | None = None

    def resolve_defaults(self, app: Flask | None = None) -> Endpoint:
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

    def to_ts(self, level: int = 1) -> str:
        def default(fmt: Fmt) -> str:
            if fmt.variable not in self.defaults:
                return ""
            d = repr(self.defaults[fmt.variable])

            return f" = {d}"

        method = str(self.methods)
        indent = INDENT * level
        m1 = f"methods: {method}"
        cargs = [fmt for fmt in self.url_fmt_arguments if not fmt.is_static]
        args = ", ".join(
            f"{fmt.variable}: {fmt.ts_type}{default(fmt)}" for fmt in cargs
        )
        q1 = '"' if "." in self.endpoint else ""
        if self.server:
            server = f"{self.server} + "
        else:
            server = ""
        url = f"url({args}) {{ return {server}`{self.url}` }}"

        fields = [m1, url]

        if self.doc:
            s = self.doc.replace("`", r"\`")
            fields.append(f"doc: `{s}`")

        if self.defaults:
            d = repr(self.defaults)
            d = "{ " + d[1:-1] + " }"
            fields.append(f"defaults: {d}")

        body = f",{NL}{indent}".join(fields)

        return f"{q1}{self.endpoint}{q1}: {{{NL}{indent}{body}{NL}{INDENT}}}"


class TypescriptAPI:
    def __init__(
        self,
        endpoints: str | Sequence[str] | None = None,
        *,
        inject_url_defaults: bool = False,
        static: bool = False,
    ):
        if endpoints is None:
            endpoints = []
        elif isinstance(endpoints, str):
            endpoints = [endpoints]
        self.endpoints = endpoints

        self.static = static
        self.inject_url_defaults = inject_url_defaults

    def get_endpoints(self, app: Flask, server: str | None = None) -> list[Endpoint]:
        ret: list[Endpoint] = []
        # capture defaults first!
        defaults: dict[str, dict[str, Any]] = defaultdict(dict)
        for r in app.url_map.iter_rules():
            if r.defaults:
                defaults[r.endpoint].update(r.defaults)
        for r in sorted(app.url_map.iter_rules(), key=lambda r: r.endpoint):
            if not r.methods or ("GET" not in r.methods and "POST" not in r.methods):
                continue
            blueprint = r.endpoint.split(".", 1)[0] if "." in r.endpoint else r.endpoint

            if self.endpoints and blueprint not in self.endpoints:
                continue
            if not self.static and "static" in r.endpoint:  # skip static
                continue
            api = self.process_rule(
                r,
                app,
                defaults=defaults[r.endpoint],
                server=server,
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
        server: str | None = None,
    ) -> Endpoint | None:
        view_func = app.view_functions[r.endpoint]
        if view_func is None:
            return None
        if r.methods is None:
            return None
        if defaults is None:
            defaults = {}

        doc = inspect.getdoc(view_func)

        # vf = unwrap(view_func)
        # if hasattr(vf, '__typescript_api__'):
        #     ts = vf.__typescript_api__
        #     print(ts)

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

        api = Endpoint(
            endpoint=r.endpoint,
            methods=sorted(filter(lambda n: n in {"GET", "POST"}, r.methods)),  # type: ignore
            doc=doc,
            rule=r.rule,
            url=url,
            url_fmt_arguments=url_fmt_arguments,
            url_arguments=url_arguments,
            defaults=defaults,
            server=server,
        )

        return api


def get_endpoints(
    app: Flask,
    endpoint: str | Sequence[str] | None = None,
    static: bool = False,
    inject_url_defaults: bool = False,
    server: str | None = None,
) -> list[Endpoint]:
    return TypescriptAPI(
        endpoint,
        inject_url_defaults=inject_url_defaults,
        static=static,
    ).get_endpoints(app, server=server)


PREAMBLE = """
export interface Endpoint {
    methods: ("GET" | "POST")[]
    url: (...args: any[]) => string
    doc?: string
    defaults?: Record<string, string | number>
}
"""


def endpoints_ts(app: Flask, out: TextIO, server: str | None = None):
    eps = [
        ep.to_ts(level=2)
        for ep in get_endpoints(
            app,
            [],
            static=False,
            server="SERVER" if server else None,
        )
    ]
    # print(ep.endpoint, ep.methods, ep.url_arguments, ep.url, ep.url_fmt_arguments)
    body = f",{NL}{INDENT}".join(eps)
    body = f"export const Endpoints = {{{NL}{INDENT}{body}{NL}}} satisfies Readonly<Record<string, Endpoint>>"
    print(PREAMBLE, file=out)
    if server is not None:
        print(f'const SERVER = "{server}"', file=out)
        print(file=out)
    print(body, file=out)
