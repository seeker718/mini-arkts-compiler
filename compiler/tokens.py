"""词法单元定义。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class TokenType(Enum):
    # ---- 字面量与标识符 ----
    NUMBER = auto()
    STRING = auto()
    TEMPLATE_STRING = auto()
    IDENTIFIER = auto()

    # ---- 关键字 ----
    LET = auto()
    CONST = auto()
    VAR = auto()
    FUNCTION = auto()
    RETURN = auto()
    IF = auto()
    ELSE = auto()
    WHILE = auto()
    FOR = auto()
    DO = auto()
    BREAK = auto()
    CONTINUE = auto()
    CLASS = auto()
    STRUCT = auto()
    INTERFACE = auto()
    EXTENDS = auto()
    IMPLEMENTS = auto()
    ENUM = auto()
    NEW = auto()
    THIS = auto()
    SUPER = auto()
    TYPEOF = auto()
    INSTANCEOF = auto()
    IN = auto()
    OF = auto()
    TRUE = auto()
    FALSE = auto()
    NULL = auto()
    UNDEFINED = auto()
    VOID = auto()
    PUBLIC = auto()
    PRIVATE = auto()
    PROTECTED = auto()
    STATIC = auto()
    READONLY = auto()
    ASYNC = auto()
    AWAIT = auto()
    IMPORT = auto()
    EXPORT = auto()
    FROM = auto()
    AS = auto()
    NUMBER_TYPE = auto()
    STRING_TYPE = auto()
    BOOLEAN_TYPE = auto()
    ANY_TYPE = auto()
    NEVER_TYPE = auto()
    SWITCH = auto()
    CASE = auto()
    DEFAULT = auto()
    TRY = auto()
    CATCH = auto()
    FINALLY = auto()
    THROW = auto()

    # ---- 运算符 ----
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    PERCENT = auto()
    ASSIGN = auto()
    PLUS_ASSIGN = auto()
    MINUS_ASSIGN = auto()
    STAR_ASSIGN = auto()
    SLASH_ASSIGN = auto()
    PERCENT_ASSIGN = auto()
    EQ = auto()
    NEQ = auto()
    STRICT_EQ = auto()
    STRICT_NEQ = auto()
    LT = auto()
    GT = auto()
    LTE = auto()
    GTE = auto()
    AND = auto()
    OR = auto()
    NOT = auto()
    BIT_AND = auto()
    BIT_OR = auto()
    BIT_XOR = auto()
    BIT_NOT = auto()
    SHL = auto()
    SHR = auto()
    USHR = auto()
    QUESTION = auto()
    COLON = auto()
    ARROW = auto()
    INCREMENT = auto()
    DECREMENT = auto()
    ELLIPSIS = auto()
    OPTIONAL_CHAIN = auto()

    # ---- 分隔符 ----
    DOT = auto()
    COMMA = auto()
    SEMICOLON = auto()
    LPAREN = auto()
    RPAREN = auto()
    LBRACE = auto()
    RBRACE = auto()
    LBRACKET = auto()
    RBRACKET = auto()

    # ---- 特殊 ----
    AT = auto()
    EOF = auto()

    def __str__(self) -> str:  # pragma: no cover - 仅用于调试输出
        return self.name


@dataclass
class Token:
    """一个词法单元。

    Attributes:
        type:   :class:`TokenType` 枚举值。
        value:  词素原文（保留原始文本，便于错误提示与代码回显）。
        line:   1 起始行号。
        column: 1 起始列号。
    """

    type: TokenType
    value: str
    line: int
    column: int

    def __repr__(self) -> str:  # pragma: no cover - 仅用于调试输出
        return f"Token({self.type.name}, {self.value!r}, {self.line}:{self.column})"

    def to_dict(self) -> dict:
        return {
            "type": self.type.name,
            "value": self.value,
            "line": self.line,
            "column": self.column,
        }