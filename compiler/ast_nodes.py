"""抽象语法树（AST）节点定义。

所有节点都继承 :class:`Node`，字段统一带默认值，方便递归下降分析器用关键字
参数构造节点。序列化在 :mod:`compiler.ast_json` 中通过 ``dataclasses.fields``
反射完成，因此新增节点无需改动序列化代码。

节点命名刻意保留 ``lineno`` / ``col``，用于实验二的语义错误定位。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Node:
    """AST 基类。"""

    lineno: int = 0
    col: int = 0


# ---------------------------------------------------------------- 顶层与块
@dataclass
class Program(Node):
    body: list = field(default_factory=list)


@dataclass
class Block(Node):
    body: list = field(default_factory=list)


# ---------------------------------------------------------------- 基础表达式
@dataclass
class Identifier(Node):
    name: str = ""


@dataclass
class Literal(Node):
    value: Any = None
    raw: str = ""
    literal_type: str = ""  # number / string / boolean / null / undefined / template


@dataclass
class ThisExpression(Node):
    pass


@dataclass
class SuperExpression(Node):
    pass


# ---------------------------------------------------------------- 类型
@dataclass
class TypeAnnotation(Node):
    name: str = ""
    type_args: list = field(default_factory=list)
    is_array: bool = False


# ---------------------------------------------------------------- 声明
@dataclass
class Decorator(Node):
    name: str = ""
    arguments: list = field(default_factory=list)


@dataclass
class Parameter(Node):
    name: str = ""
    type_annotation: Optional[TypeAnnotation] = None
    default: Optional[Node] = None
    rest: bool = False


@dataclass
class VariableDeclaration(Node):
    kind: str = "let"  # let / const / var
    name: str = ""
    type_annotation: Optional[TypeAnnotation] = None
    init: Optional[Node] = None
    decorators: list = field(default_factory=list)


@dataclass
class FunctionDeclaration(Node):
    name: str = ""
    params: list = field(default_factory=list)
    return_type: Optional[TypeAnnotation] = None
    body: Optional[Block] = None
    decorators: list = field(default_factory=list)
    modifiers: list = field(default_factory=list)


@dataclass
class ClassDeclaration(Node):
    kind: str = "class"  # class / struct / interface
    name: str = ""
    extends: Optional[str] = None
    implements: list = field(default_factory=list)
    members: list = field(default_factory=list)
    decorators: list = field(default_factory=list)


@dataclass
class MethodDeclaration(Node):
    name: str = ""
    params: list = field(default_factory=list)
    return_type: Optional[TypeAnnotation] = None
    body: Optional[Block] = None
    decorators: list = field(default_factory=list)
    modifiers: list = field(default_factory=list)


@dataclass
class FieldDeclaration(Node):
    name: str = ""
    type_annotation: Optional[TypeAnnotation] = None
    init: Optional[Node] = None
    decorators: list = field(default_factory=list)
    modifiers: list = field(default_factory=list)


# ---------------------------------------------------------------- 语句
@dataclass
class ExpressionStatement(Node):
    expression: Optional[Node] = None


@dataclass
class IfStatement(Node):
    test: Optional[Node] = None
    consequent: Optional[Node] = None
    alternate: Optional[Node] = None


@dataclass
class WhileStatement(Node):
    test: Optional[Node] = None
    body: Optional[Node] = None


@dataclass
class DoWhileStatement(Node):
    body: Optional[Node] = None
    test: Optional[Node] = None


@dataclass
class ForStatement(Node):
    init: Optional[Node] = None
    test: Optional[Node] = None
    update: Optional[Node] = None
    body: Optional[Node] = None


@dataclass
class ReturnStatement(Node):
    argument: Optional[Node] = None


@dataclass
class BreakStatement(Node):
    pass


@dataclass
class ContinueStatement(Node):
    pass


# ---------------------------------------------------------------- 表达式
@dataclass
class AssignmentExpression(Node):
    operator: str = "="
    left: Optional[Node] = None
    right: Optional[Node] = None


@dataclass
class BinaryExpression(Node):
    operator: str = ""
    left: Optional[Node] = None
    right: Optional[Node] = None


@dataclass
class LogicalExpression(Node):
    operator: str = ""
    left: Optional[Node] = None
    right: Optional[Node] = None


@dataclass
class UnaryExpression(Node):
    operator: str = ""
    operand: Optional[Node] = None
    prefix: bool = True


@dataclass
class UpdateExpression(Node):
    operator: str = ""
    argument: Optional[Node] = None
    prefix: bool = True


@dataclass
class ConditionalExpression(Node):
    test: Optional[Node] = None
    consequent: Optional[Node] = None
    alternate: Optional[Node] = None


@dataclass
class CallExpression(Node):
    callee: Optional[Node] = None
    arguments: list = field(default_factory=list)


@dataclass
class NewExpression(Node):
    callee: Optional[Node] = None
    arguments: list = field(default_factory=list)


@dataclass
class MemberExpression(Node):
    object: Optional[Node] = None
    property: Optional[Node] = None
    computed: bool = False


@dataclass
class ArrayLiteral(Node):
    elements: list = field(default_factory=list)


@dataclass
class Property(Node):
    key: Optional[Node] = None
    value: Optional[Node] = None
    computed: bool = False
    shorthand: bool = False


@dataclass
class ObjectLiteral(Node):
    properties: list = field(default_factory=list)


@dataclass
class ArrowFunctionExpression(Node):
    params: list = field(default_factory=list)
    body: Optional[Node] = None
    is_expression: bool = True


# ---------------------------------------------------------------- 鸿蒙声明式 UI
@dataclass
class UiContainer(Node):
    """ArkUI 声明式 UI 组件容器，如 ``Column() { Text('hi') }``。

    ``name`` 是组件名（Column / Row / List ...），``arguments`` 是构造参数，
    ``children`` 是尾随块中的子组件语句列表。这是 ArkTS 相对 TypeScript 最
    典型的语法扩展，实验一的验收重点。
    """

    name: str = ""
    arguments: list = field(default_factory=list)
    children: list = field(default_factory=list)