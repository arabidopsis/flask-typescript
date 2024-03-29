from __future__ import annotations

import json
import math
import re
from collections.abc import Hashable
from datetime import datetime
from typing import Any
from typing import Callable

from .constants import HOLE
from .constants import NAN
from .constants import NEGATIVE_INFINITY
from .constants import NEGATIVE_ZERO
from .constants import POSITIVE_INFINITY
from .constants import UNDEFINED

# python implemntation of https://github.com/Rich-Harris/devalue/blob/master/src/parse.js

undefined = object()  # fake undefined


def hashable(o: Any) -> bool:
    return isinstance(o, Hashable)


REVIVERS = dict[str, Callable[[Any], Any]]


def parse(serialized: str, revivers: REVIVERS | None = None) -> Any:
    return unflatten(json.loads(serialized), revivers)


def unflatten(  # noqa: C901
    values: list[Any] | int,
    revivers: REVIVERS | None = None,
) -> Any:
    revivers = revivers or {}

    def hydrate(index: int, standalone: bool = False) -> Any:
        if index == UNDEFINED:
            # raise ValueError("can't implement undefined!")
            return undefined
        if index == NAN:
            return math.nan
        if index == POSITIVE_INFINITY:
            return math.inf
        if index == NEGATIVE_INFINITY:
            return -math.inf
        if index == NEGATIVE_ZERO:
            return -0

        if standalone:
            raise ValueError(f"Invalid input {index}")

        if index in hydrated:
            return hydrated[index]

        if isinstance(values, int):
            raise ValueError("expecting dict")

        value = values[index]

        if not value or not isinstance(value, (dict, list)):
            # string , numbers, etc
            hydrated[index] = value
        elif isinstance(value, list):
            if isinstance(value[0], str):
                typeval = value[0]
                assert revivers is not None
                reviver = revivers.get(typeval)
                if reviver is not None:
                    hydrated[index] = ret = reviver(hydrate(value[1]))
                    return ret

                if typeval == "Date":
                    hydrated[index] = datetime.fromisoformat(value[1])

                elif typeval == "Set":
                    hydrated[index] = s = set()
                    for v in value[1:]:
                        s.add(hydrate(v))

                elif typeval == "Map":
                    hydrated[index] = mapd = {}
                    for i in range(1, len(value), 2):
                        key = hydrate(value[i])
                        if not hashable(key):
                            raise ValueError(f"Invalid key for Map: {key}")
                        mapd[key] = hydrate(value[i + 1])

                elif typeval == "null":
                    hydrated[index] = mapd = {}
                    for i in range(1, len(value), 2):
                        mapd[value[i]] = hydrate(value[i + 1])

                elif typeval == "RegExp":
                    flags = 0
                    FLAGS = {
                        "i": re.IGNORECASE,
                        "m": re.MULTILINE,
                        "s": re.DOTALL,
                        "g": 0,  # FIXME: Can't do global!!!
                    }
                    if len(value) == 3:
                        for f in value[2]:  # gims
                            flags |= FLAGS.get(f, 0)

                    hydrated[index] = re.compile(value[1], flags)

                elif typeval == "Object":
                    # Boolean,String,Number... just use the value
                    hydrated[index] = value[1]

                elif typeval == "BigInt":
                    # python integers are big!
                    hydrated[index] = int(value[1])

                else:
                    raise ValueError(f"Unknown type {typeval}")

            else:
                hydrated[index] = array = [HOLE] * len(value)
                for i, n in enumerate(value):
                    if n == HOLE:  # can't do holes!
                        raise ValueError("can't do holes in Arrays!")
                    array[i] = hydrate(n)

        else:
            hydrated[index] = obj = {}
            for key, n in value.items():
                obj[key] = hydrate(n)

        return hydrated[index]

    hydrated: dict[int, Any] = {}

    if isinstance(values, int):
        return hydrate(values, True)

    if not isinstance(values, list) or len(values) == 0:
        raise ValueError(f"Invalid input {type(values)}")

    return hydrate(0)


if __name__ == "__main__":
    # use https://svelte.dev/repl/138d70def7a748ce9eda736ef1c71239?version=3.49.0
    # to get strings to test...
    import sys
    from pprint import pprint

    pprint(parse(sys.argv[1]))
