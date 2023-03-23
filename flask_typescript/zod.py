from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import replace
from typing import Any


def zodargs(z: ZOD) -> dict[str, Any]:
    d = asdict(z)
    d = {
        k: v
        for k, v in d.items()
        if v is not None and k not in {"key", "prev", "value"}
    }
    return d


@dataclass
class ZOD:
    key: str
    value: tuple[Any, ...] = ()
    prev: ZOD | None = None

    def array(self):
        return ZOD(key="array", prev=self)

    def noarg(self, name: str) -> ZOD:
        return ZOD(key=name, prev=self)

    def optional(self):
        return self.noarg("optional")

    def to_z(self) -> str:
        key, rest = self.key, self.value
        if key in {"object", "tuple"}:
            d = rest[0]
            args = str(d)
            t = f"{key}({args})"
        else:
            t = f"{key}()"
        return t

    def to_ts(self) -> str:
        key, rest = self.key, self.value
        if key == "tuple":
            args = ",".join([r.ts() for r in rest[0]])
            return f"[{args}]"
        if key == "union":
            argl: list[str] = [r.ts() for r in rest[0]]
            if "null" in argl and argl[-1] != "null":
                argl.remove("null")
                argl = argl + ["null"]
            return "|".join(argl)

        if key == "map":
            k, v = rest
            return f"{{ [name: {k.ts()}]: {v.ts()} }}"
        if key == "object":
            d = rest[0]
            d = [f"{k}: {v.ts()}" for k, v in d.items()]

            return "{\t" + "\n\t".join(d) + "\n}"
        if key == "array":
            return "[]"
        if key == "optional":
            return "?"
        if key == "number":
            return key
        if key == "literal":
            return rest[0]

        return key

    def _getlist(self) -> list[ZOD]:
        ret = [self]
        prev = self.prev
        while prev is not None:
            ret.append(prev)
            prev = prev.prev
        ret = list(reversed(ret))
        return ret

    def __str__(self):
        ret = self._getlist()
        if ret and isinstance(ret[0], RefZod):
            r = []
        else:
            r = ["z"]
        for z in ret:
            r.append(z.to_z())
        return ".".join(r)

    def ts(self) -> str:
        zlist = self._getlist()
        r: list[str] = []
        for z, p in zip(zlist, [ZOD(key="_start_")] + zlist[:-1]):
            if z.key == "array":
                assert p is not None
                if p.key == "union":
                    # wrap...
                    r[-1] = f"({r[-1]})"
            r.append(z.to_ts())
        return "".join(r)

    def __repr__(self):
        return str(self)


@dataclass(repr=False)
class RefZod(ZOD):
    def to_z(self) -> str:
        return self.key

    def to_ts(self) -> str:
        return self.key


@dataclass(repr=False)
class StringZod(ZOD):
    max_: int | None = None
    min_: int | None = None

    def max(self, n: int) -> StringZod:
        return replace(self, max_=n)

    def min(self, n: int) -> StringZod:
        return replace(self, min_=n)

    def datetime(self) -> ZOD:
        return self.noarg("datetime")

    def to_z(self):
        d = zodargs(self)
        r = ["string()"]
        for k, v in d.items():
            r.append(f"{k[:-1]}({v})")

        return ".".join(r)

    def to_ts(self):
        return "string"


class BigZed:
    def map(self, k: ZOD, value: ZOD) -> ZOD:
        return ZOD(key="map", value=(k, value))

    def string(self) -> StringZod:
        return StringZod(key="string")

    def date(self) -> ZOD:
        return self.noarg("date")

    def boolean(self) -> ZOD:
        return self.noarg("boolean")

    def set(self, k: ZOD) -> ZOD:
        return ZOD(key="set", value=(k,))

    def tuple(self, args: list[ZOD]) -> ZOD:
        return ZOD(key="tuple", value=(args,))

    def union(self, args: list[ZOD]) -> ZOD:
        return ZOD(key="union", value=(args,))

    def number(self):
        return self.noarg("number")

    def any(self):
        return self.noarg("any")

    def object(self, objs: dict[str, ZOD]) -> ZOD:
        return ZOD(key="object", value=(objs,))

    def noarg(self, name: str) -> ZOD:
        return ZOD(key=name)

    def array(self, val: ZOD) -> ZOD:
        return val.array()

    def literal(self, val: Any) -> ZOD:
        return ZOD(key="literal", value=(val,))

    def optional(self, val: ZOD) -> ZOD:
        return val.optional()

    def ref(self, name: str) -> RefZod:
        return RefZod(key=name)
