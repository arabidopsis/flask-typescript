from __future__ import annotations

import re


NUMBER = re.compile(r"^\d+(\.\d*)?$")
Number = {
    "1": "one",
    "2": "two",
    "3": "three",
    "4": "four",
    "5": "five",
    "6": "six",
    "7": "seven",
    "8": "eight",
    "9": "nine",
    "0": "zero",
}


def pascal_case(name: str) -> str:
    name = "".join(n[0].upper() + n[1:] for n in name.split("_"))
    if name.endswith("s"):
        name = name[:-1]
    name = name.replace(".", "_")
    if name in {"Column", "Table", "Integer"}:
        name = name + "Class"
    return name


def pyname(name: str) -> str:
    name = name.strip()
    if name.isidentifier():
        return name
    if name[0].isdigit():
        name = Number[name[0]] + name[1:]
    name = clean(name)
    return name


def quote(s: str) -> str:
    for q in ['"', "'"]:
        if s.startswith(q) and s.endswith(q):
            if NUMBER.match(s[1:-1]):
                return s
    return f'"{s}"'


def chop(s: str) -> str:
    for q in ['"', "'"]:
        if s.startswith(q) and s.endswith(q):
            return s[1:-1]
    return s


def clean(s: str) -> str:
    """replace non words or digits with underscores"""
    return re.sub(r"\W|^(?=\d)", "_", s)


def jsname(name: str) -> str:
    return pyname(name)
