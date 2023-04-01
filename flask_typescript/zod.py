from __future__ import annotations

from abc import abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from dataclasses import field


class ZOD:
    def __str__(self) -> str:
        return self.to_ts()

    @abstractmethod
    def to_ts(self) -> str:
        raise NotImplementedError("need to implement typscript generation")

    @abstractmethod
    def get_generic_args(self) -> list[ZOD]:
        raise NotImplementedError("need to implement typscript generation")

    def to_generic_args(self):
        return ", ".join([t.to_generic_args() for t in self.get_generic_args()])

    @property
    def is_generic(self) -> bool:
        return len(self.get_generic_args()) > 0

    def array(self) -> ZOD:
        ts = self.to_ts()
        args = f"({ts})[]" if "|" in ts else f"{ts}[]"
        return StrZOD(str_type=args, generic=self.get_generic_args())

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
    generic: list[ZOD] = field(default_factory=list)

    def get_generic_args(self) -> list[ZOD]:
        return self.generic

    def to_ts(self) -> str:
        return self.str_type


@dataclass
class GenericZOD(ZOD):
    str_type: str
    typename: str = ""  # basic generic typename
    constraints: list[ZOD] | None = None

    def to_ts(self) -> str:
        return self.str_type

    def get_generic_args(self) -> list[ZOD]:
        return [self]

    def to_generic_args(self) -> str:
        if not self.constraints:
            return self.typename

        constraints = ZZZ.union(self.constraints)
        return f"{self.typename}= {constraints.to_ts()}"

    def array(self) -> ZOD:
        ts = self.to_ts()
        args = f"({ts})[]" if "|" in ts else f"{ts}[]"
        return GenericZOD(
            str_type=args,
            typename=self.typename,
            constraints=self.constraints,
        )


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

    def _generic(self, args: Sequence[ZOD]) -> list[ZOD]:
        return [g for i in args if i.is_generic for g in i.get_generic_args()]

    def to_generic_args(self, args: Sequence[ZOD]) -> str:
        generics = ZZZ._generic(args)
        if not generics:
            return ""
        _args = {t.to_generic_args(): t for t in generics}.keys()
        val = ", ".join(_args)
        return f"<{val}>"

    def tuple(self, args: Sequence[ZOD]) -> ZOD:
        _args = list(args)
        sargs = "[" + ",".join(i.to_ts() for i in _args) + "]"
        return StrZOD(str_type=sargs, generic=self._generic(_args))

    def union(self, args: list[ZOD]) -> ZOD:
        null = self.null()
        if null in args and args[-1] != null:
            args.remove(null)
            args = args + [null]
        # str|bytes => string|string => string
        # there is not ordered set...so we use an ordered dict
        _args = {i.to_ts(): i for i in args}.keys()

        sargs = " | ".join(_args)
        return StrZOD(str_type=sargs, generic=self._generic(args))

    def map(self, k: ZOD, v: ZOD) -> ZOD:
        args = f"{{ [name: {k.to_ts()}]: {v.to_ts()} }}"

        return StrZOD(str_type=args, generic=self._generic([k, v]))

    def literal(self, r: str) -> ZOD:
        return StrZOD(str_type=r)

    def object(self, fields: Sequence[TSField]) -> ZOD:
        _args = list(fields)
        sfields = ", ".join(f.to_ts() for f in _args)

        return StrZOD(str_type=sfields, generic=self._generic(_args))

    def function(self, args: Sequence[TSField], returntype: ZOD) -> ZOD:
        _args = list(args)
        sargs = ", ".join(f.to_ts() for f in _args)
        # FIXME generic (a)
        generic = self._generic(_args + [returntype])
        if generic:
            val = ", ".join(g.to_generic_args() for g in generic)
            val = f"<{val}>"
        else:
            val = ""

        return StrZOD(
            str_type=f"{val}({sargs})=> {returntype.to_ts()}",
            generic=generic,
        )

    def typevar(self, name: str, args: list[ZOD]) -> ZOD:
        return GenericZOD(str_type=name, typename=name, constraints=args)


ZZZ = BigZed()


@dataclass
class TSField(ZOD):
    arg: ZOD
    name: str
    default: str | None = None

    def get_generic_args(self) -> list[ZOD]:
        return self.arg.get_generic_args()

    def to_ts(self) -> str:
        args = self.arg.to_ts()
        default = "" if self.default is None else f" /* ={self.default} */"
        q = "?" if self.default is not None else ""
        return f"{self.name}{q}: {args}{default}"

    def anonymous(self) -> ZOD:
        return self.arg


assert ZZZ.null() == ZZZ.null()
