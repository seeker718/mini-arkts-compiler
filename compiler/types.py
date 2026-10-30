"""ArkTS 子集的类型系统（实验二）。

设计目标：体现方舟编译器「去动态化」的严格静态类型思想——
``number`` 与 ``string`` 之间不存在隐式转换，赋值、运算、传参都必须类型匹配。

类型用统一的 :class:`Type` 数据类表示，通过 :class:`TypeKind` 区分种类；
用户定义的 class / struct / interface 由 :class:`TypeRegistry` 统一登记，
并负责成员查找与子类型判定。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto


class TypeKind(Enum):
    NUMBER = auto()
    STRING = auto()
    BOOLEAN = auto()
    VOID = auto()
    NULL = auto()
    UNDEFINED = auto()
    ANY = auto()
    NEVER = auto()
    ARRAY = auto()
    FUNCTION = auto()
    CLASS = auto()
    INTERFACE = auto()
    UNION = auto()
    UNKNOWN = auto()


@dataclass
class MemberInfo:
    """类 / 接口的成员信息。"""

    name: str
    type: "Type"
    visibility: str = "public"  # public / private / protected
    kind: str = "field"  # field / method
    decorators: list = field(default_factory=list)
    node: object = None


@dataclass
class Type:
    kind: TypeKind
    name: str = ""
    element: "Type | None" = None  # 数组元素类型
    param_types: list = field(default_factory=list)  # 函数参数类型
    return_type: "Type | None" = None  # 函数返回类型
    members: dict = field(default_factory=dict)  # name -> MemberInfo
    bases: list = field(default_factory=list)  # 父类 / 接口名
    variants: list = field(default_factory=list)  # 联合类型成员

    def __str__(self) -> str:
        if self.name:
            return self.name
        if self.kind is TypeKind.ARRAY:
            return f"{self.element}[]"
        if self.kind is TypeKind.FUNCTION:
            params = ", ".join(str(p) for p in self.param_types)
            return f"({params}) => {self.return_type}"
        if self.kind is TypeKind.UNION:
            return " | ".join(str(v) for v in self.variants)
        return self.kind.name.lower()

    def is_primitive(self) -> bool:
        return self.kind in _PRIMITIVE_KINDS


_PRIMITIVE_KINDS = {
    TypeKind.NUMBER, TypeKind.STRING, TypeKind.BOOLEAN,
    TypeKind.VOID, TypeKind.NULL, TypeKind.UNDEFINED, TypeKind.ANY, TypeKind.NEVER,
}

# ---------------------------------------------------------------- 预定义类型
NUMBER = Type(TypeKind.NUMBER, "number")
STRING = Type(TypeKind.STRING, "string")
BOOLEAN = Type(TypeKind.BOOLEAN, "boolean")
VOID = Type(TypeKind.VOID, "void")
NULL = Type(TypeKind.NULL, "null")
UNDEFINED = Type(TypeKind.UNDEFINED, "undefined")
ANY = Type(TypeKind.ANY, "any")
NEVER = Type(TypeKind.NEVER, "never")
UNKNOWN = Type(TypeKind.UNKNOWN, "<unknown>")

PRIMITIVES: dict[str, Type] = {
    "number": NUMBER,
    "string": STRING,
    "boolean": BOOLEAN,
    "void": VOID,
    "null": NULL,
    "undefined": UNDEFINED,
    "any": ANY,
    "never": NEVER,
}


def array_of(element: Type) -> Type:
    return Type(TypeKind.ARRAY, f"{element}[]", element=element)


def function_type(param_types: list, return_type: Type) -> Type:
    return Type(TypeKind.FUNCTION, param_types=list(param_types), return_type=return_type)


def union_of(variants: list) -> Type:
    return Type(TypeKind.UNION, variants=list(variants))


class TypeRegistry:
    """用户定义类型（class / struct / interface）的登记表。"""

    def __init__(self) -> None:
        self._types: dict[str, Type] = {}

    def register(self, t: Type) -> None:
        self._types[t.name] = t

    def lookup(self, name: str) -> Type | None:
        return self._types.get(name)

    def resolve(self, name: str) -> Type | None:
        """先查预定义类型，再查用户类型；查不到返回 None。"""
        return PRIMITIVES.get(name) or self._types.get(name)

    def member(self, t: Type, name: str) -> MemberInfo | None:
        """在本类型及其全部基类中查找成员。"""
        seen: set[str] = set()
        stack = [t]
        while stack:
            current = stack.pop()
            if not current.name or current.name in seen:
                continue
            seen.add(current.name)
            if name in current.members:
                return current.members[name]
            for base_name in current.bases:
                base = self._types.get(base_name)
                if base:
                    stack.append(base)
        return None

    def is_subtype(self, sub: Type, sup: Type) -> bool:
        if sub is sup or (sub.name and sub.name == sup.name):
            return True
        if sub.kind not in (TypeKind.CLASS, TypeKind.INTERFACE):
            return False
        seen: set[str] = set()
        stack = [sub]
        while stack:
            current = stack.pop()
            if not current.name or current.name in seen:
                continue
            seen.add(current.name)
            for base_name in current.bases:
                if base_name == sup.name:
                    return True
                base = self._types.get(base_name)
                if base:
                    stack.append(base)
        return False


def is_assignable(src: Type, dst: Type, registry: TypeRegistry) -> bool:
    """判断 ``src`` 类型的值能否赋值给 ``dst`` 类型的变量。

    这是「去动态化」的核心：number 与 string 之间返回 False，
    不存在隐式转换。
    """
    if src is dst or (src.name and src.name == dst.name):
        return True
    if dst.kind is TypeKind.ANY or src.kind is TypeKind.ANY:
        return True
    if src.kind is TypeKind.NEVER:
        return True
    if src.kind is TypeKind.UNKNOWN or dst.kind is TypeKind.UNKNOWN:
        return True  # 未知类型不重复报错，避免级联噪音
    if src.kind in (TypeKind.NULL, TypeKind.UNDEFINED):
        return dst.kind in (TypeKind.CLASS, TypeKind.INTERFACE, TypeKind.ARRAY, TypeKind.UNION, TypeKind.ANY)
    if dst.kind is TypeKind.UNION:
        return any(is_assignable(src, v, registry) for v in dst.variants)
    if src.kind is TypeKind.UNION:
        return all(is_assignable(v, dst, registry) for v in src.variants)
    if src.kind is TypeKind.ARRAY and dst.kind is TypeKind.ARRAY:
        return is_assignable(src.element, dst.element, registry)
    if src.kind is TypeKind.FUNCTION and dst.kind is TypeKind.FUNCTION:
        if len(src.param_types) != len(dst.param_types):
            return False
        params_ok = all(
            is_assignable(d, s, registry)
            for s, d in zip(src.param_types, dst.param_types)
        )
        return params_ok and is_assignable(src.return_type, dst.return_type, registry)
    if src.kind in (TypeKind.CLASS, TypeKind.INTERFACE) and dst.kind in (TypeKind.CLASS, TypeKind.INTERFACE):
        return registry.is_subtype(src, dst)
    return False