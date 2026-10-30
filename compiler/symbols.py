"""符号表与作用域管理（实验二）。

作用域链按 ArkTS 的实际嵌套关系组织，形成「全局 → 组件/类 → 方法 → 块」
的多级结构。组件作用域中同时存放状态（@State 等字段）与方法，
对应大纲要求的「组件-状态-方法」三级作用域管理。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from .types import Type

__all__ = ["SymbolKind", "Symbol", "Scope", "SymbolTable"]


class SymbolKind(Enum):
    VARIABLE = auto()
    CONSTANT = auto()
    PARAMETER = auto()
    FUNCTION = auto()
    CLASS = auto()
    STRUCT = auto()
    INTERFACE = auto()
    FIELD = auto()
    METHOD = auto()


@dataclass
class Symbol:
    name: str
    kind: SymbolKind
    type: Type | None = None
    node: object = None
    decorators: list = field(default_factory=list)
    modifiers: list = field(default_factory=list)
    scope: str = ""
    lineno: int = 0
    col: int = 0
    inferred: bool = False

    def is_state(self) -> bool:
        return any(d in _STATE_DECORATORS for d in self.decorators)

    def __str__(self) -> str:
        return f"{self.kind.name.lower()} {self.name}: {self.type}"


_STATE_DECORATORS = {
    "State", "Prop", "Link", "Provide", "Consume", "ObjectLink",
    "Observed", "Watch", "StorageLink", "StorageProp",
    "LocalStorageLink", "LocalStorageProp", "Track",
}


class Scope:
    """一个作用域，持有若干符号，并可向上层作用域查找。"""

    def __init__(self, kind: str, name: str, parent: "Scope | None" = None) -> None:
        self.kind = kind  # global / class / function / block
        self.name = name
        self.parent = parent
        self.symbols: dict[str, Symbol] = {}

    def define(self, symbol: Symbol) -> Symbol | None:
        """在当前作用域定义符号；若同名已存在则返回已存在的符号。"""
        if symbol.name in self.symbols:
            return self.symbols[symbol.name]
        symbol.scope = self.name
        self.symbols[symbol.name] = symbol
        return None

    def lookup_local(self, name: str) -> Symbol | None:
        return self.symbols.get(name)

    def __str__(self) -> str:
        return f"<scope {self.kind}:{self.name}>"


class SymbolTable:
    """作用域栈。"""

    def __init__(self) -> None:
        self.global_scope = Scope("global", "<global>", None)
        self.stack: list[Scope] = [self.global_scope]

    @property
    def current(self) -> Scope:
        return self.stack[-1]

    def push(self, kind: str, name: str) -> Scope:
        scope = Scope(kind, name, self.current)
        self.stack.append(scope)
        return scope

    def pop(self) -> Scope:
        if len(self.stack) == 1:
            raise RuntimeError("不能弹出全局作用域")
        return self.stack.pop()

    def define(self, symbol: Symbol) -> Symbol | None:
        return self.current.define(symbol)

    def resolve(self, name: str) -> Symbol | None:
        """自内向外查找符号。"""
        scope: Scope | None = self.current
        while scope is not None:
            found = scope.lookup_local(name)
            if found is not None:
                return found
            scope = scope.parent
        return None

    def resolve_local(self, name: str) -> Symbol | None:
        return self.current.lookup_local(name)

    def in_global(self) -> bool:
        return self.current is self.global_scope

    def current_class(self):
        """返回最近的一个 class 作用域（用于 this / 成员可见性判定）。"""
        for scope in reversed(self.stack):
            if scope.kind == "class":
                return scope
        return None