from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ZOD:
    str_type: str

    def __str__(self) -> str:
        return self.str_type

    def array(self) -> ZOD:
        args = f"({self.str_type})[]" if "|" in self.str_type else f"{self.str_type}[]"
        return ZOD(str_type=args)

    def as_async(self) -> ZOD:
        return ZOD(str_type=f"Promise<{self.str_type}>")

    def field(
        self,
        name: str,
        default: str | None = None,
    ) -> TSField:
        return TSField(
            str_type=self.str_type,
            name=name,
            default=default,
        )


class BigZed:
    def any(self) -> ZOD:
        return ZOD(str_type="any")

    def void(self) -> ZOD:
        return ZOD(str_type="void")

    def null(self) -> ZOD:
        return ZOD(str_type="null")

    def string(self) -> ZOD:
        return ZOD(str_type="string")

    def number(self) -> ZOD:
        return ZOD(str_type="number")

    def boolean(self) -> ZOD:
        return ZOD(str_type="boolean")

    def File(self) -> ZOD:
        return ZOD(str_type="File")

    def unknown(self) -> ZOD:
        return ZOD(str_type="unknown")

    def ref(self, name: str) -> ZOD:
        return ZOD(str_type=name)

    def tuple(self, args: list[ZOD]) -> ZOD:
        sargs = "[" + ",".join(i.str_type for i in args) + "]"
        return ZOD(str_type=sargs)

    def union(self, iargs: list[ZOD]) -> ZOD:
        _args = sorted(iargs, key=lambda z: z.str_type)
        null = self.null()
        if null in _args and _args[-1] != null:
            _args.remove(null)
            _args = _args + [null]
        sargs = " | ".join(i.str_type for i in _args)
        return ZOD(str_type=sargs)

    def map(self, k: ZOD, v: ZOD) -> ZOD:
        args = f"{{ [name: {k.str_type}]: {v.str_type} }}"
        return ZOD(str_type=args)

    def literal(self, r: str) -> ZOD:
        return ZOD(str_type=r)

    # def object(self, fields:dict[str,ZOD]) -> ZOD:
    #     v = ','.join(f'{name}: {z.str_type}' for name,z in fields.items())
    #     return ZOD(str_type = '{' + v +'}')


ZZZ = BigZed()


@dataclass
class TSField(ZOD):
    name: str
    default: str | None = None

    def make_default(self) -> str:
        fmt = " /* ={} */"
        return "" if self.default is None else fmt.format(self.default)

    def to_ts(self) -> str:
        default = self.make_default()
        q = "?" if self.default is not None else ""
        return f"{self.name}{q}: {self.str_type}{default}"

    def __str__(self) -> str:
        return self.to_ts()

    def is_typed(self) -> bool:
        return self.str_type not in {"any", "unknown"}

    def anonymous(self) -> ZOD:
        return ZOD(str_type=self.str_type)
