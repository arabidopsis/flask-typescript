from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass


class ZOD:
    def __str__(self) -> str:
        return self.to_ts()

    @abstractmethod
    def to_ts(self) -> str:
        raise NotImplementedError("need to implement typscript generation")

    def array(self) -> ZOD:
        ts = self.to_ts()
        args = f"({ts})[]" if "|" in ts else f"{ts}[]"
        return StrZOD(str_type=args)

    def as_async(self) -> ZOD:
        return StrZOD(str_type=f"Promise<{self.to_ts()}>")

    def as_result(self) -> ZOD:
        return StrZOD(str_type=f"Result<{self.to_ts()}>")

    def field(
        self,
        name: str,
        default: str | None = None,
    ) -> TSField:
        return TSField(
            arg=self,
            name=name,
            default=default,
        )


@dataclass
class StrZOD(ZOD):
    str_type: str

    def to_ts(self) -> str:
        return self.str_type


class BigZed:
    def any(self) -> ZOD:
        return StrZOD(str_type="any")

    def void(self) -> ZOD:
        return StrZOD(str_type="void")

    def null(self) -> ZOD:
        return StrZOD(str_type="null")

    def string(self) -> ZOD:
        return StrZOD(str_type="string")

    def number(self) -> ZOD:
        return StrZOD(str_type="number")

    def boolean(self) -> ZOD:
        return StrZOD(str_type="boolean")

    def File(self) -> ZOD:
        return StrZOD(str_type="File")

    def unknown(self) -> ZOD:
        return StrZOD(str_type="unknown")

    def ref(self, name: str) -> ZOD:
        return StrZOD(str_type=name)

    def tuple(self, args: list[ZOD]) -> ZOD:
        sargs = "[" + ",".join(i.to_ts() for i in args) + "]"
        return StrZOD(str_type=sargs)

    def union(self, iargs: list[ZOD]) -> ZOD:
        null = self.null()
        if null in iargs and iargs[-1] != null:
            iargs.remove(null)
            iargs = iargs + [null]
        sargs = " | ".join(i.to_ts() for i in iargs)
        return StrZOD(str_type=sargs)

    def map(self, k: ZOD, v: ZOD) -> ZOD:
        args = f"{{ [name: {k.to_ts()}]: {v.to_ts()} }}"
        return StrZOD(str_type=args)

    def literal(self, r: str) -> ZOD:
        return StrZOD(str_type=r)

    def object(self, fields: list[TSField]) -> ZOD:
        sfields = ", ".join(f.to_ts() for f in fields)
        return StrZOD(str_type=sfields)

    def function(self, args: list[TSField], returntype: ZOD) -> ZOD:
        sargs = ", ".join(f.to_ts() for f in args)
        return StrZOD(str_type=f"({sargs})=> {returntype.to_ts()}")


ZZZ = BigZed()


@dataclass
class TSField(ZOD):
    arg: ZOD
    name: str
    default: str | None = None

    def to_ts(self) -> str:
        default = "" if self.default is None else f" /* ={self.default} */"
        q = "?" if self.default is not None else ""
        return f"{self.name}{q}: {self.arg.to_ts()}{default}"

    def anonymous(self) -> ZOD:
        return self.arg


assert ZZZ.null() == ZZZ.null()
