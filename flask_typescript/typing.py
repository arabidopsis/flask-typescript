from __future__ import annotations

import collections
import decimal
from abc import ABCMeta
from abc import abstractmethod
from collections.abc import Mapping
from collections.abc import Sequence
from dataclasses import dataclass
from dataclasses import Field
from dataclasses import fields
from dataclasses import is_dataclass
from dataclasses import MISSING
from dataclasses import replace
from datetime import date
from datetime import datetime
from enum import Enum
from importlib import import_module
from inspect import signature
from types import FunctionType
from typing import Any
from typing import Callable
from typing import cast
from typing import ForwardRef
from typing import get_args
from typing import get_origin
from typing import get_type_hints
from typing import Iterator
from typing import Literal
from typing import Type
from typing import TypeGuard
from typing import TypeVar
from typing import Union

from pydantic import BaseModel
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined
from werkzeug.datastructures import FileStorage

from .orm.sqla_typing import find_mapped_default
from .orm.sqla_typing import is_declarative
from .orm.sqla_typing import is_mapped_column
from .utils import lenient_issubclass
from .zod import TSField
from .zod import ZOD
from .zod import ZZZ

try:
    from typing import is_typeddict
except ImportError:

    def is_typeddict(tp: object) -> bool:
        from typing import _TypedDictMeta  # type: ignore

        return isinstance(tp, _TypedDictMeta)


INDENT = "    "
NL = "\n"

TSTypeable = Union[Type[Any], Callable[..., Any]]

TSThing = Union["TSFunction", "TSInterface", "TSEnum"]


def is_dataclass_type(obj: Any) -> bool:
    return isinstance(obj, type) and is_dataclass(obj)


def is_pydantic_type(typ: Any) -> TypeGuard[type[BaseModel]]:
    return isinstance(typ, type) and issubclass(typ, BaseModel)


def is_file_storage(typ: Any) -> bool:
    return isinstance(typ, type) and issubclass(typ, FileStorage)


def get_dc_defaults(cls: type[Any]) -> dict[str, Any]:
    if not is_dataclass_type(cls):
        raise TypeError(
            f"{cls} is not a dataclass type",
        )

    def get_default(f: Field[Any]) -> Any:
        if f.default_factory is not MISSING:
            return f.default_factory()
        if f.default is not MISSING:
            ret = f.default
            if is_mapped_column(ret):  # possibly sqlalchemy dataclass
                ret = find_mapped_default(ret)
            return ret
        return MISSING

    return {
        f.name: d for f in fields(cls) for d in [get_default(f)] if d is not MISSING
    }


# def get_py_defaults2(cls: type[Any]) -> dict[str, Any]:
#     if not is_pydantic_type(cls):
#         raise TypeError(
#             f"{cls} is not a subclass of pydantic.BaseModel",
#         )

#     def get_default(f: Any) -> Any:
#         if "default" in f:
#             return f["default"]
#         return MISSING

#     schema = cls.schema()

#     return {
#         name: d
#         for name, f in schema["properties"].items()
#         for d in [get_default(f)]
#         if d is not MISSING
#     }


def get_py_fields(cls: type[Any]) -> dict[str, FieldInfo]:
    return cls.model_fields  # type: ignore


def get_py_defaults(cls: type[Any]) -> dict[str, Any]:
    # using schema doesn't give any defaults from Field(default_factory...) types
    if not is_pydantic_type(cls):
        raise TypeError(
            f"{cls} is not a subclass of pydantic.BaseModel",
        )

    def get_default(f: FieldInfo) -> Any:
        r = f.default

        if r is PydanticUndefined:
            return MISSING
        return r

    return {
        name: d
        for name, f in get_py_fields(cls).items()
        for d in [get_default(f)]
        if d is not MISSING
    }


@dataclass
class Annotation:
    name: str
    type: type[Any]
    default: Any

    @property
    def has_default(self) -> bool:
        return self.default is not MISSING

    @property
    def requires_post(self) -> bool:
        return is_file_storage(self.type)


def get_annotations(
    cls_or_func: TSTypeable,
    ns: Any | None = None,
) -> dict[str, Annotation]:
    """Return the anntotations for a dataclass or function.

    May throw a `NameError` if annotation is only imported when
    typing.TYPE_CHECKING is True.
    """
    d = get_type_hints(cls_or_func, localns=ns, include_extras=False)
    if isinstance(cls_or_func, FunctionType):
        sig = signature(cls_or_func)
        defaults = {
            k: v.default for k, v in sig.parameters.items() if v.default is not v.empty
        }
        # add untyped parameters
        d_ = {k: d.get(k, Any) for k in sig.parameters}
        if "return" in d:
            d_["return"] = d["return"]
        d = d_
    elif is_typeddict(cls_or_func):
        defaults = {}
    elif is_pydantic_type(cls_or_func):
        defaults = get_py_defaults(cls_or_func)
        # if "__concrete__" in d and issubclass(cls_or_func, BaseModel):
        #     del d["__concrete__"]
    else:
        if "__clsname__" in d and is_declarative(cls_or_func):
            del d["__clsname__"]
        defaults = get_dc_defaults(cast(Type[Any], cls_or_func))

    return {k: Annotation(k, v, defaults.get(k, MISSING)) for k, v in d.items()}


@dataclass
class TSInterface:
    name: str
    fields: list[TSField]

    export: bool = True
    indent: str = INDENT
    nl: str = NL
    interface: Literal["interface", "type", "namespace"] = "namespace"

    @property
    def is_generic(self) -> bool:
        return any(f.is_generic for f in self.fields)

    # def get_generics(self) -> list[ZOD]:
    #     ret = [f.arg for f in self.fields if f.is_generic]
    #     return ret

    def to_ts(self) -> str:
        def ts_fields() -> str:
            astype = self.interface == "namespace"
            nl = self.nl
            return nl.join(
                f"{self.indent}{f.to_ts(astype=astype)}" for f in self.fields
            )

        export = "export " if self.export else ""
        nl = self.nl
        eq = ""
        if self.interface == "type":
            eq = "= "

        return f"{export}{self.interface} {self.name}{self._generic_args()} {eq}{{{nl}{ts_fields()}{nl}}}"

    def _generic_args(self) -> str:
        return ZZZ.to_generic_args(self.fields)

    def anonymous(self) -> ZOD:
        return ZZZ.object(self.fields)

    def __str__(self) -> str:
        return self.to_ts()


@dataclass
class TSFunction:
    name: str
    args: list[TSField]
    returntype: ZOD

    export: bool = True
    isasync: bool = False
    result: bool = False

    def remove_args(self, *args: str) -> TSFunction:
        a = [f for f in self.args if f.name not in set(args)]
        return replace(self, args=a)

    def to_ts(self) -> str:
        def ts_args() -> str:
            return ", ".join(f.to_ts() for f in self.args)

        sargs = ts_args()
        export = "export " if self.export else ""
        generics = self._generic_args()
        return (
            f"{export}type {self.name}{generics} = ({sargs}) => {self.async_returntype}"
        )

    def anonymous(self) -> ZOD:
        return ZZZ.function(self.args, self.async_returntype)

    def __str__(self) -> str:
        return self.to_ts()

    @property
    def async_returntype(self) -> ZOD:
        rt = self.returntype
        if self.result:
            rt = rt.as_result()
        if self.isasync:
            return rt.as_async()
        return rt

    def _generic_args(self) -> str:
        return ZZZ.to_generic_args(self.args + [self.returntype])


@dataclass
class TSEnum:
    name: str
    fields: list[ZOD]
    export: bool = True

    def to_ts(self) -> str:
        args = " | ".join(f.to_ts() for f in self.fields)
        export = "export " if self.export else ""
        return f"{export}type {self.name} = {args}"

    def anonymous(self) -> ZOD:
        return ZZZ.union(self.fields)

    def __str__(self) -> str:
        return self.to_ts()


class BaseBuilder(metaclass=ABCMeta):
    def __init__(self, ns: dict[str, Any] | None = None):
        self.build_stack: list[TSTypeable] = []
        self.ns = ns
        self.seen: dict[str, str] = {}
        self.built: set[str] = set()

    def get_annotations(self, cls: TSTypeable) -> dict[str, Annotation]:
        return get_annotations(cls, self.ns)

    def is_being_built(self, o: TSTypeable) -> bool:
        return any(o == s for s in self.build_stack)

    def current_module(self) -> dict[str, Any]:
        if self.build_stack:
            m = import_module(self.build_stack[-1].__module__)
            return m.__dict__
        return {}

    # pylint: disable=too-many-return-statements
    def ts_repr(self, value: Any) -> str:
        ts_repr = self.ts_repr
        if value is None:
            return "null"
        if isinstance(value, FunctionType):  # field(default_factory=lambda:...)
            return ts_repr(value())
        if isinstance(value, decimal.Decimal):
            return repr(float(value))
        if isinstance(value, str):  # WARNING: *before* test for Sequence!
            return repr(value)
        if isinstance(value, bytes):  # WARNING: *before* test for Sequence!
            return repr(value)[1:]  # chop b off b'xxx'
        if isinstance(value, collections.abc.Sequence):
            args = ", ".join(ts_repr(v) for v in value)
            return f"[{args}]"
        if isinstance(value, collections.abc.Mapping):
            args = ", ".join(f"{str(k)}: {ts_repr(v)}" for k, v in value.items())
            return f"{{{args}}}"
        if isinstance(value, bool):
            return repr(value).lower()
        # whatever...
        return repr(value)

    def process_seen(
        self,
        seen: dict[str, str] | None = None,
    ) -> Iterator[Callable[[], TSThing | None]]:
        if seen is None:
            seen = {}
        seen.update(self.seen)
        self.seen = {}
        for name in self.built:
            if name in seen:
                del seen[name]

        for name, module in seen.items():
            yield self.create_builder(name, module)

    @abstractmethod
    def get_type_ts(self, o: TSTypeable) -> TSThing:
        return NotImplemented

    def create_builder(self, name: str, module: str) -> Callable[[], TSThing | None]:
        def build_func() -> TSThing | None:
            m = import_module(module)
            typ = getattr(m, name)
            ok = is_dataclass_type(typ) or is_pydantic_type(typ)
            if not ok:
                return None
            return self.get_type_ts(typ)

        return build_func


def toz(s: str) -> ZOD:
    return getattr(ZZZ, s)()  # type: ignore[no-any-return]


DEFAULTS: dict[type[Any], ZOD] = {
    str: toz("string"),
    int: toz("number"),
    float: toz("number"),
    type(None): toz("null"),
    bytes: toz("string"),  # TODO see if this works
    bool: toz("boolean"),
    decimal.Decimal: toz("number"),
    FileStorage: toz("File"),
    date: toz("string"),
    datetime: toz("string"),
}


class TSBuilder(BaseBuilder):
    TS = DEFAULTS.copy()

    def __init__(
        self,
        ns: dict[str, Any] | None = None,  # local namespace for typing.get_type_hints
        *,
        use_name: bool = True,  # use name for dataclasses, pydantic classes
        ignore_defaults: bool = False,
    ):
        super().__init__(ns)
        self.use_name = use_name
        self.ignore_defaults = ignore_defaults

    def process_seen(
        self,
        seen: dict[str, str] | None = None,
    ) -> Iterator[Callable[[], TSThing | None]]:
        if seen is None:
            seen = {}
        seen.update(self.seen)
        self.seen = {}
        for name in self.built:
            if name in seen:
                del seen[name]

        for name, module in seen.items():
            yield self.create_builder(name, module)

    def __call__(self, o: TSTypeable) -> TSThing:
        return self.get_type_ts(o)

    def forward_ref(self, type_name: str) -> ZOD:
        if type_name in self.seen:
            return ZZZ.ref(type_name)
        g = self.current_module()
        if type_name in g:
            typ = g[type_name]
            if not isinstance(typ, str):
                return self.type_to_zod(typ)
        if self.use_name:
            return ZZZ.ref(type_name)
        raise TypeError(f'unknown ForwardRef "{type_name}"')

    def arglist_to_zod(self, types: Sequence[type[Any]]) -> list[ZOD]:
        iargs = [
            self.type_to_zod(s, is_arg=True)
            for s in types
            if s  # type: ignore[comparison-overlap]
            is not Ellipsis  # e.g. t.Tuple[int,...]
        ]
        return iargs

    def typevar_to_zod(self, typ: TypeVar) -> ZOD:
        args = (typ.__bound__,) if typ.__bound__ else typ.__constraints__
        iargs = self.arglist_to_zod(args)
        return ZZZ.typevar(typ.__name__, iargs)

    def type_to_zod(self, typ: type[Any], is_arg: bool = False) -> ZOD:
        if is_dataclass_type(typ) or is_pydantic_type(typ):
            if (
                self.is_being_built(typ)
                or is_arg
                or typ.__name__ in self.seen
                or typ.__name__ in self.built
                or self.use_name
            ):  # recursive
                self.seen[typ.__name__] = typ.__module__
                return ZZZ.ref(typ.__name__)  # just use name
            ret = self.get_type_ts(typ)
            # we are going to annonymize it e.g. => {key: number[], key2:string}
            # because we don't need full `export type Name = {....}`
            self.built.remove(ret.name)
            return ret.anonymous()

        if isinstance(typ, ForwardRef):
            return self.forward_ref(typ.__forward_arg__)
        if isinstance(typ, TypeVar):
            return self.typevar_to_zod(typ)

        # e.g. cls is the <class 'list'> while typ is list[int]
        cls = get_origin(typ)
        if cls is None:
            cls = typ

        is_type = isinstance(cls, type)
        targs = get_args(typ)
        if targs:
            iargs = self.arglist_to_zod(targs)

            if is_type and issubclass(cls, Mapping):
                # e.g. dict[str, int]
                k, v = iargs
                args = ZZZ.map(k, v)
            else:
                if is_type and issubclass(cls, tuple):
                    # tuple types
                    # we need to bail early here since
                    # we are not now a ts list (e.g. val[])
                    return ZZZ.tuple(iargs)
                else:
                    if len(iargs) == 1:
                        args = iargs[0]
                    else:
                        # assume Union
                        args = ZZZ.union(iargs)
        else:
            if is_type:
                if cls not in self.TS:
                    self.seen[cls.__name__] = cls.__module__
                    return ZZZ.ref(cls.__name__)
                args = self.TS[cls]
            else:
                if isinstance(cls, str) and not is_arg:
                    return self.forward_ref(cls)
                if typ == Any:
                    return ZZZ.any()
                args = ZZZ.literal(self.ts_repr(cls))  # Literal

        if (
            is_type
            and issubclass(cls, (collections.abc.Sequence, collections.abc.Set))
            and not issubclass(
                cls,
                (str, bytes),
            )  # these are both sequences but not arrays
        ):
            args = args.array()
        return args

    def get_field_types(
        self,
        cls: TSTypeable,
        is_arg: bool = False,
    ) -> Iterator[TSField]:
        a = self.get_annotations(cls)

        for name, annotation in a.items():
            ts_type_as_zod = self.type_to_zod(annotation.type, is_arg=is_arg)
            yield ts_type_as_zod.field(
                name=name,
                default=self.ts_repr(annotation.default)
                if annotation.has_default and not self.ignore_defaults
                else None,
            )

    def get_dc_ts(self, typ: type[Any]) -> TSInterface:
        fieldslist = list(self.get_field_types(typ))
        return TSInterface(
            name=typ.__name__,
            fields=fieldslist,
            interface="type",
        )

    def get_func_ts(self, func: Callable[..., Any]) -> TSFunction:
        if not callable(func):
            raise TypeError(f"{func} is not a function")

        ft = list(self.get_field_types(func, is_arg=True))
        args = [f for f in ft if f.name != "return"]
        rt = [f for f in ft if f.name == "return"]
        if rt:
            returntype = rt[0].anonymous()
            if (
                returntype == ZZZ.null()
            ):  # type(None) for a return type should mean void
                returntype = ZZZ.void()
        else:
            returntype = ZZZ.unknown()

        return TSFunction(name=func.__name__, args=args, returntype=returntype)

    def get_type_ts(self, o: TSTypeable) -> TSThing:
        # main entrypoint
        self.build_stack.append(o)
        try:
            ret: TSThing
            if isinstance(o, FunctionType):
                ret = self.get_func_ts(cast(Callable[..., Any], o))
            elif lenient_issubclass(o, Enum):
                ret = self.get_enum_ts(cast(type[Enum], o))
            else:
                ret = self.get_dc_ts(cast(Type[Any], o))
                self.built.add(ret.name)
                if ret.name in self.seen:
                    del self.seen[ret.name]
            return ret
        finally:
            self.build_stack.pop()

    def get_enum_ts(self, enum: type[Enum]) -> TSEnum:
        return TSEnum(
            name=enum.__name__,
            fields=[ZZZ.literal(self.ts_repr(v.value)) for v in enum],
        )
