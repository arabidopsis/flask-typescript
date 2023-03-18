from __future__ import annotations

import collections
import decimal
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import Field
from dataclasses import fields
from dataclasses import is_dataclass
from dataclasses import MISSING
from dataclasses import replace
from datetime import date
from importlib import import_module
from inspect import signature
from types import FunctionType
from typing import Any
from typing import Callable
from typing import cast
from typing import ForwardRef
from typing import get_type_hints
from typing import Iterator
from typing import Type
from typing import Union

from pydantic import BaseModel
from werkzeug.datastructures import FileStorage


INDENT = "    "
NL = "\n"

TSTypeable = Union[Type[Any], Callable[..., Any]]

TSThing = Union["TSFunction", "TSInterface"]


def is_dataclass_instance(obj: Any) -> bool:
    return is_dataclass(obj) and not isinstance(obj, type)


def is_dataclass_type(obj: Any) -> bool:
    return is_dataclass(obj) and isinstance(obj, type)


def is_pydantic_type(typ: type[Any]) -> bool:
    return isinstance(typ, type) and issubclass(typ, BaseModel)


def is_typeddict(o):
    from typing import _TypedDictMeta

    return isinstance(o, _TypedDictMeta)


def get_dc_defaults(cls: type[Any]) -> dict[str, Any]:
    if not is_dataclass_type(cls):
        raise TypeError(
            f"{cls} is not a dataclass type instance={is_dataclass_instance(cls)}",
        )

    def get_default(f: Field) -> Any:
        if f.default is not MISSING:
            return f.default
        if f.default_factory is not MISSING:  # type: ignore
            return f.default_factory()  # type: ignore
        return MISSING

    return {
        f.name: d for f in fields(cls) for d in [get_default(f)] if d is not MISSING
    }


def get_py_defaults2(cls: type[Any]) -> dict[str, Any]:
    if not is_pydantic_type(cls):
        raise TypeError(
            f"{cls} is not a subclass of pydantic.BaseModel",
        )

    def get_default(f) -> Any:
        if "default" in f:
            return f["default"]
        return MISSING

    schema = cls.schema()

    return {
        name: d
        for name, f in schema["properties"].items()
        for d in [get_default(f)]
        if d is not MISSING
    }


def get_py_defaults(cls: type[Any]) -> dict[str, Any]:
    # using schema doesn't give any defaults from Field(...) types
    if not is_pydantic_type(cls):
        raise TypeError(
            f"{cls} is not a subclass of pydantic.BaseModel",
        )

    def get_default(f) -> Any:
        r = f.get_default()
        if r is None and not f.allow_none:
            return MISSING
        return r

    return {
        name: d
        for name, f in cls.__fields__.items()
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
        # TODO: typing.List[F]
        return isinstance(self.type, type) and issubclass(self.type, FileStorage)


def get_annotations(
    cls_or_func: TSTypeable,
    ns: Any | None = None,
) -> dict[str, Annotation]:
    """Return the anntotations for a dataclass or function.

    May throw a `NameError` if annotation is only imported when
    typing.TYPE_CHECKING is True.
    """
    if isinstance(cls_or_func, FunctionType):
        sig = signature(cls_or_func)
        defaults = {
            k: v.default for k, v in sig.parameters.items() if v.default is not v.empty
        }
        d_ = get_type_hints(cls_or_func, localns=ns)
        # add untyped parameters
        d = {k: d_.get(k, Any) for k in sig.parameters}
        if "return" in d_:
            d["return"] = d_["return"]
    elif is_typeddict(cls_or_func):
        defaults = {}
        d = get_type_hints(cls_or_func, localns=ns)
    elif is_pydantic_type(cls_or_func):  # type: ignore
        defaults = get_py_defaults(cast(Type[Any], cls_or_func))
        d = get_type_hints(cls_or_func, localns=ns)
    else:
        defaults = get_dc_defaults(cast(Type[Any], cls_or_func))
        # we want the type of the field as it is on the
        # client (browser) side e.g. bytes -> number[]
        # d = {f.name: get_field_type(f) for f in fields(cls_or_func)}
        d = get_type_hints(cls_or_func, localns=ns)

    return {k: Annotation(k, v, defaults.get(k, MISSING)) for k, v in d.items()}


@dataclass
class TSField:
    name: str
    type: str
    requires_post: bool = False  # e.g. for FileStorage
    default: str | None = None
    colon: str = ": "

    @property
    def is_list(self):
        self.type.endswith("[]")  # convention

    @property
    def nested_type(self):
        assert self.is_list, self
        return self.type[:-2]

    def make_default(self, as_comment: bool = True):
        if as_comment:
            fmt = " /* ={} */"
        else:
            fmt = " ={}"
        return "" if self.default is None else fmt.format(self.default)

    def to_ts(
        self,
        with_default: bool = True,
        with_optional: bool = False,
        as_comment: bool = True,
    ) -> str:
        if with_default:
            default = self.make_default(as_comment)
        else:
            default = ""
        q = "?" if with_optional and self.default is not None else ""
        return f"{self.name}{q}{self.colon}{self.type}{default}"

    def __str__(self) -> str:
        return self.to_ts()

    def is_typed(self) -> bool:
        return self.type not in {"any", "unknown"}


@dataclass
class TSInterface:
    name: str
    fields: list[TSField]
    indent: str = INDENT
    export: bool = True
    nl: str = NL
    with_defaults: bool = True
    interface: str = "interface"

    def to_ts(self) -> str:
        export = "export " if self.export else ""
        nl = self.nl
        eq = "= " if self.interface == "type" else ""
        return (
            f"{export}{self.interface} {self.name} {eq}{{{nl}{self.ts_fields()}{nl}}}"
        )

    def ts_fields(self):
        nl = self.nl
        return nl.join(
            f"{self.indent}{f.to_ts(with_default=self.with_defaults, with_optional=True)}"
            for f in self.fields
        )

    def anonymous(self) -> str:
        sfields = ", ".join(
            f.to_ts(with_default=self.with_defaults) for f in self.fields
        )
        return f"{{ {sfields} }}"

    def is_typed(self) -> bool:
        return all(f.is_typed() for f in self.fields)

    def __str__(self) -> str:
        return self.to_ts()


@dataclass
class TSFunction:
    name: str
    args: list[TSField]
    returntype: str
    export: bool = True
    with_defaults: bool = True
    body: str | None = None
    nl: str = NL
    indent: str = INDENT
    isasync: bool = False

    @property
    def requires_post(self) -> bool:
        return any(f.requires_post for f in self.args)

    def remove_args(self, *args: str) -> TSFunction:
        a = [f for f in self.args if f.name not in set(args)]
        return replace(self, args=a)

    def to_ts(self, **kwargs) -> str:
        sargs = self.ts_args()
        export = "export " if self.export else ""
        if self.body is None:
            return f"{export}type {self.name} = ({sargs}) => {self.async_returntype}"

        return f"{export}const {self.name} = ({sargs}): {self.async_returntype} =>{self.ts_body()}"

    def ts_args(self) -> str:
        return ", ".join(
            f.to_ts(
                with_default=self.with_defaults,
                with_optional=True,
                as_comment=self.body is None,
            )
            for f in self.args
        )

    def ts_body(self) -> str:
        if self.body is None:
            return ""
        nl = self.nl
        tab = f"{nl}{self.indent}"
        body = tab.join(self.body.splitlines())
        return f" {{{tab}{body}{tab}}}"

    def __str__(self) -> str:
        return self.to_ts()

    def anonymous(self) -> str:
        sargs = self.ts_args()
        arrow = " =>" if self.body is None else ":"
        return f"({sargs}){arrow} {self.async_returntype}{self.ts_body()}"

    def is_typed(self) -> bool:
        return all(f.is_typed() for f in self.args) and self.returntype not in {
            "any",
            "unknown",
        }

    @property
    def async_returntype(self) -> str:
        if self.isasync:
            return f"Promise<{self.returntype}>"
        return self.returntype


DEFAULTS: dict[type[Any], str] = {
    str: "string",
    int: "number",
    float: "number",
    type(None): "null",
    bytes: "string",  # TODO see if this works
    bool: "boolean",
    decimal.Decimal: "number",
    FileStorage: "File",
    date: "string",
}


class TSBuilder:
    TS = DEFAULTS.copy()

    def __init__(
        self,
        ns: Any | None = None,  # local namespace for typing.get_type_hints
    ):
        self.build_stack: list[TSTypeable] = []
        self.seen: dict[str, str] = {}
        self.ns = ns
        self.built: set[str] = set()

    def process_seen(
        self,
        seen: dict[str, str] | None = None,
    ) -> Iterator[Callable[[], TSThing]]:
        if seen is None:
            seen = {}
        seen.update(self.seen)
        self.seen = {}

        for name, module in seen.items():
            yield self.create_builder(name, module)

    def create_builder(self, name: str, module: str) -> Callable[[], TSThing]:
        def build_func():
            m = import_module(module)
            return self.get_type_ts(getattr(m, name))

        return build_func

    def __call__(self, o: TSTypeable) -> TSThing:
        return self.get_type_ts(o)

    def forward_ref(self, type_name: str) -> str:
        if type_name in self.seen:
            return type_name
        g = self.current_module()
        if type_name in g:
            typ = g[type_name]
            if not isinstance(typ, str):
                return self.type_to_str(typ)
        raise TypeError(f'unknown ForwardRef "{type_name}"')

    def type_to_str(self, typ: type[Any], is_arg: bool = False) -> str:
        if is_dataclass_type(typ) or is_pydantic_type(typ):
            if (
                self.is_being_built(typ)
                or is_arg
                or typ.__name__ in self.seen
                or typ.__name__ in self.built
            ):  # recursive
                if is_arg:
                    self.seen[typ.__name__] = typ.__module__
                return typ.__name__  # just use name
            ret = self.get_type_ts(typ)
            self.built.remove(ret.name)  # we are going to annonomize it
            return ret.anonymous()

        if isinstance(typ, ForwardRef):
            return self.forward_ref(typ.__forward_arg__)

        if hasattr(typ, "__origin__"):
            cls = typ.__origin__
        else:
            cls = typ  # list, str, etc.

        is_type = isinstance(cls, type)
        if hasattr(typ, "__args__"):
            iargs = (
                self.type_to_str(s, is_arg=True)
                for s in typ.__args__
                if s is not Ellipsis  # e.g. t.Tuple[int,...]
            )

            if is_type and issubclass(cls, Mapping):
                k, v = iargs
                args = f"{{ [name: {k}]: {v} }}"
            else:
                # Union,List
                _args = sorted(set(iargs))
                if "null" in _args and _args[-1] != "null":
                    _args.remove("null")
                    _args = _args + ["null"]
                args = " | ".join(_args)
        else:
            if is_type:
                if cls not in self.TS:
                    self.seen[cls.__name__] = cls.__module__
                    return cls.__name__
                    # raise TypeError(
                    #     f"unknown type: {typ.__qualname__} from {cls.__module__}"
                    # )
                args = self.TS[cls]
            else:
                if isinstance(cls, str) and not is_arg:
                    return self.forward_ref(cls)
                if typ == Any:
                    return "any"
                args = self.ts_repr(cls)  # Literal

        if (
            is_type
            and issubclass(cls, collections.abc.Sequence)
            and not issubclass(
                cls,
                (str, bytes),
            )  # these are both sequences but not arrays
        ):
            args = f"({args})[]" if "|" in args else f"{args}[]"
        return args

    def get_field_types(
        self,
        cls: TSTypeable,
        is_arg: bool = False,
    ) -> Iterator[TSField]:
        a = get_annotations(cls, self.ns)

        for name, annotation in a.items():
            ts_type_as_str = self.type_to_str(annotation.type, is_arg=is_arg)
            yield TSField(
                name=name,
                type=ts_type_as_str,
                requires_post=annotation.requires_post,
                default=self.ts_repr(annotation.default)
                if annotation.has_default
                else None,
            )

    def get_dc_ts(self, typ: type[Any]) -> TSInterface:
        return TSInterface(
            name=typ.__name__,
            fields=list(self.get_field_types(typ)),
            interface="type",
        )

    def get_func_ts(self, func: Callable[..., Any]) -> TSFunction:
        if not callable(func):
            raise TypeError(f"{func} is not a function")

        ft = list(self.get_field_types(func, is_arg=True))
        args = [f for f in ft if f.name != "return"]
        rt = [f for f in ft if f.name == "return"]
        if rt:
            returntype = rt[0].type
            if returntype == "null":  # type(None) for a return type should mean void
                returntype = "void"
        else:
            returntype = "unknown"

        return TSFunction(name=func.__name__, args=args, returntype=returntype)

    def is_being_built(self, o: TSTypeable) -> bool:
        return any(o == s for s in self.build_stack)

    def get_type_ts(self, o: TSTypeable) -> TSThing:
        # main entrypoint
        self.build_stack.append(o)
        try:
            ret: TSThing
            if isinstance(o, FunctionType):
                ret = self.get_func_ts(cast(Callable[..., Any], o))
            else:
                ret = self.get_dc_ts(cast(Type[Any], o))
                self.built.add(ret.name)
            return ret
        finally:
            self.build_stack.pop()

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
            return repr(value)[1:]  # chop b'xxx' off
        if isinstance(value, collections.abc.Sequence):
            args = ", ".join(ts_repr(v) for v in value)
            return f"[{args}]"
        if isinstance(value, collections.abc.Mapping):
            args = ", ".join(f"{str(k)}: {ts_repr(v)}" for k, v in value.items())
            return f"{{{args}}}"
        if isinstance(value, bool):
            return repr(value).lower()
        # if isinstance(value, (float, int)):
        #     return s
        return repr(value)
