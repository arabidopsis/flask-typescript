from __future__ import annotations

import re
from typing import Any
from typing import Iterator

from werkzeug.datastructures import ImmutableMultiDict

ARG = re.compile(r"\[([^]]*)\]")


def lenient_issubclass(
    cls: Any,
    class_or_tuple: type[Any] | tuple[type[Any], ...] | None,
) -> bool:
    return isinstance(cls, type) and issubclass(cls, class_or_tuple)  # type: ignore[arg-type]


def flatten(json: dict[str, Any]) -> Iterator[tuple[str, Any]]:
    """flatten a nested dictionary into a top level dictionary with "dotted" keys"""
    for key, val in json.items():
        if isinstance(val, dict):
            for k, v in flatten(val):
                yield f"{key}.{k}", v
        else:
            yield key, val


# php keys are like:


# draw: 6
# columns[0][data]: protein_name
# columns[0][name]:
# columns[0][searchable]: true
# columns[0][orderable]: true
# columns[0][search][value]:
# columns[0][search][regex]: false


def ijquery_keys(key: str) -> Iterator[str]:
    start = 0
    for m in ARG.finditer(key):
        prev = key[start : m.start()]
        if prev:
            yield prev
        yield m.group(1)
        start = m.end()
    prev = key[start:]
    if prev:
        yield prev


def jquery_keys(key: str) -> list[str]:
    return list(ijquery_keys(key))


# names that are just [0] are invalid
# [0]: val1
# [1]: val2
def jquery_json(form: ImmutableMultiDict) -> dict[str, Any]:
    ret: dict[str, Any] = {}

    def ensure(lst, idx):
        while len(lst) <= idx:
            lst.append({})

    for fullkey, val in form.items():
        keylist = jquery_keys(fullkey)
        tgt = ret
        prefix, key = keylist[:-1], keylist[-1]
        if len(prefix) == 0 and key.isdigit():
            raise ValueError(f"illegal key {fullkey}")
        # print(prefix, key)
        for k, nxt in zip(prefix, keylist[1:]):
            if k == "":  # from a[]
                k = str(len(tgt))
            if k.isdigit():
                i = int(k)
                ensure(tgt, i)
                tgt = tgt[i]  # type: ignore
            else:
                if k not in tgt:
                    tgt[k] = [] if nxt.isdigit() else {}
                tgt = tgt[k]

        if key == "":  # from a[]
            key = str(len(tgt))
        if key.isdigit():
            i = int(k)
            ensure(tgt, i)
            tgt[i] = val  # type: ignore
        else:
            tgt[key] = val

    return ret


def jquery_form(form: ImmutableMultiDict) -> ImmutableMultiDict:
    return ImmutableMultiDict(flatten(jquery_json(form)))
