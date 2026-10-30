"""语义分析与类型检查（实验二）。

在实验一生成的 AST 之上完成三类工作：

1. 符号表构建：建立「全局 → 组件/类 → 方法 → 块」的多级作用域，
   登记变量、函数、类、接口、字段与方法，并检测重复定义；
2. 类型检查：实现 ArkTS 的严格静态类型规则——``number`` 与 ``string``
   之间禁止隐式转换，赋值、二元运算、函数传参、返回都要类型匹配；
3. 装饰器语义校验：检查 ``@State`` 等状态装饰器是否定义在 ``@Entry``
   组件内（模拟鸿蒙运行时的约束）。

所有错误都带行列位置，便于 IDE / 自动化测试精确定位。
"""

from __future__ import annotations

from .ast_nodes import (
    ArrayLiteral,
    ArrowFunctionExpression,
    AssignmentExpression,
    BinaryExpression,
    Block,
    BreakStatement,
    CallExpression,
    ClassDeclaration,
    ConditionalExpression,
    ContinueStatement,
    DoWhileStatement,
    ExpressionStatement,
    FieldDeclaration,
    ForStatement,
    FunctionDeclaration,
    Identifier,
    IfStatement,
    Literal,
    LogicalExpression,
    MemberExpression,
    MethodDeclaration,
    NewExpression,
    ObjectLiteral,
    Program,
    ReturnStatement,
    SuperExpression,
    ThisExpression,
    TypeAnnotation,
    UiContainer,
    UnaryExpression,
    UpdateExpression,
    VariableDeclaration,
    WhileStatement,
)
from .diagnostics import Diagnostic
from .symbols import Symbol, SymbolKind, SymbolTable
from .types import (
    ANY,
    BOOLEAN,
    NEVER,
    NULL,
    NUMBER,
    STRING,
    UNDEFINED,
    UNKNOWN,
    VOID,
    MemberInfo,
    Type,
    TypeKind,
    TypeRegistry,
    array_of,
    function_type,
    is_assignable,
    union_of,
)

# 状态类装饰器：只能用于组件状态字段
STATE_DECORATORS = {
    "State", "Prop", "Link", "Provide", "Consume", "ObjectLink",
    "Watch", "StorageLink", "StorageProp", "LocalStorageLink", "LocalStorageProp",
}

_ARITH_OPS = {"+", "-", "*", "/", "%"}
_RELATIONAL_OPS = {"<", ">", "<=", ">="}
_EQUALITY_OPS = {"==", "!=", "===", "!=="}
_BITWISE_OPS = {"&", "|", "^", "<<", ">>", ">>>"}
_COMPOUND_OPS = {"+=", "-=", "*=", "/=", "%="}


class SemanticAnalyzer:
    """对 AST 做语义分析，返回诊断列表。"""

    def __init__(self, filename: str = "<source>") -> None:
        self.filename = filename
        self.errors: list[Diagnostic] = []
        self._reported: set[tuple] = set()
        self.symbols = SymbolTable()
        self.registry = TypeRegistry()
        self.node_types: dict[int, Type] = {}
        self.structs: set[str] = set()
        self.entries: set[str] = set()
        # class 名 -> 直接父类名（只含 extends，不含 implements）。
        # 用于判定「成员是否已实现」时避免把接口自身的方法算作实现。
        self.class_extends: dict[str, str | None] = {}
        self.current_class_type: Type | None = None
        self.current_return: Type | None = None
        self.loop_depth = 0
        self.ui_depth = 0

    # ------------------------------------------------------------ 对外接口
    def analyze(self, program: Program) -> list[Diagnostic]:
        self._declare(program)
        self._check_program(program)
        return self.errors

    def type_of(self, node) -> Type:
        return self.node_types.get(id(node), UNKNOWN)

    # ------------------------------------------------------------ 诊断
    def _error(self, node, message: str) -> None:
        line = getattr(node, "lineno", 0)
        col = getattr(node, "col", 0)
        key = (line, col, message)
        if key in self._reported:
            return
        self._reported.add(key)
        self.errors.append(Diagnostic(message, line, col, "error", "sema", self.filename))

    # ------------------------------------------------------------ 第一遍：声明
    def _declare(self, program: Program) -> None:
        # 1) 先登记所有 class / struct / interface 的空壳，支持相互引用
        for stmt in program.body:
            if isinstance(stmt, ClassDeclaration):
                kind = TypeKind.INTERFACE if stmt.kind == "interface" else TypeKind.CLASS
                bases = ([stmt.extends] if stmt.extends else []) + list(stmt.implements)
                t = Type(kind, stmt.name, bases=bases)
                self.registry.register(t)
                self.symbols.define(
                    Symbol(stmt.name, SymbolKind.STRUCT if stmt.kind == "struct"
                           else SymbolKind.INTERFACE if stmt.kind == "interface"
                           else SymbolKind.CLASS,
                           type=t, node=stmt, decorators=[d.name for d in stmt.decorators],
                           lineno=stmt.lineno, col=stmt.col)
                )
                self.class_extends[stmt.name] = stmt.extends
                if stmt.kind == "struct":
                    self.structs.add(stmt.name)
                if any(d.name == "Entry" for d in stmt.decorators):
                    self.entries.add(stmt.name)

        # 2) 填充类的成员（此时所有类型都已在注册表中）
        for stmt in program.body:
            if isinstance(stmt, ClassDeclaration):
                self._fill_members(stmt)

        # 3) 声明函数与全局变量
        for stmt in program.body:
            if isinstance(stmt, FunctionDeclaration):
                self._declare_function(stmt)
            elif isinstance(stmt, VariableDeclaration):
                self._declare_global_variable(stmt)

        # 4) 检查接口实现（所有成员已就绪）
        for stmt in program.body:
            if isinstance(stmt, ClassDeclaration) and stmt.implements:
                self._check_implements(stmt)

    def _declare_function(self, stmt: FunctionDeclaration) -> None:
        param_types = [self._resolve_annotation(p.type_annotation) for p in stmt.params]
        ret = self._resolve_annotation(stmt.return_type)
        ftype = function_type(param_types, ret)
        existing = self.symbols.define(
            Symbol(stmt.name, SymbolKind.FUNCTION, type=ftype, node=stmt,
                   decorators=[d.name for d in stmt.decorators],
                   lineno=stmt.lineno, col=stmt.col)
        )
        if existing is not None:
            self._error(stmt, f"函数 '{stmt.name}' 重复定义")

    def _declare_global_variable(self, stmt: VariableDeclaration) -> None:
        declared = self._resolve_annotation(stmt.type_annotation) if stmt.type_annotation else None
        kind = SymbolKind.CONSTANT if stmt.kind == "const" else SymbolKind.VARIABLE
        existing = self.symbols.define(
            Symbol(stmt.name, kind, type=declared or UNKNOWN, node=stmt,
                   lineno=stmt.lineno, col=stmt.col, inferred=declared is None)
        )
        if existing is not None:
            self._error(stmt, f"标识符 '{stmt.name}' 重复定义")

    def _fill_members(self, stmt: ClassDeclaration) -> None:
        class_type = self.registry.lookup(stmt.name)
        if class_type is None:
            return
        for member in stmt.members:
            if isinstance(member, FieldDeclaration):
                class_type.members[member.name] = MemberInfo(
                    name=member.name,
                    type=self._resolve_annotation(member.type_annotation),
                    visibility=_visibility(member.modifiers),
                    kind="field",
                    decorators=[d.name for d in member.decorators],
                    node=member,
                )
            elif isinstance(member, MethodDeclaration):
                param_types = [self._resolve_annotation(p.type_annotation) for p in member.params]
                class_type.members[member.name] = MemberInfo(
                    name=member.name,
                    type=function_type(param_types, self._resolve_annotation(member.return_type)),
                    visibility=_visibility(member.modifiers),
                    kind="method",
                    decorators=[d.name for d in member.decorators],
                    node=member,
                )

    def _check_implements(self, stmt: ClassDeclaration) -> None:

        for iface_name in stmt.implements:
            iface = self.registry.lookup(iface_name)
            if iface is None:
                self._error(stmt, f"未定义的接口 '{iface_name}'")
                continue
            for name in iface.members:
                if not self._has_member(stmt.name, name):
                    self._error(
                        stmt,
                        f"类 '{stmt.name}' 声明实现接口 '{iface_name}'，但未实现成员 '{name}'",
                    )

    def _has_member(self, class_name: str, member_name: str) -> bool:
        """只沿 extends 链查找成员，不把 implements 的接口成员算作已实现。"""
        seen: set[str] = set()
        current: str | None = class_name
        while current and current not in seen:
            seen.add(current)
            t = self.registry.lookup(current)
            if t is None:
                break
            if member_name in t.members:
                return True
            current = self.class_extends.get(current)
        return False

    # ------------------------------------------------------------ 第二遍：检查
    def _check_program(self, program: Program) -> None:
        for stmt in program.body:
            if isinstance(stmt, ClassDeclaration):
                self._check_class(stmt)
            elif isinstance(stmt, FunctionDeclaration):
                self._check_function(stmt)
            elif isinstance(stmt, VariableDeclaration):
                self._check_variable_init(stmt)
            else:
                self.check(stmt)

    def _check_class(self, stmt: ClassDeclaration) -> None:
        class_type = self.registry.lookup(stmt.name)
        self.symbols.push("class", stmt.name)
        previous = self.current_class_type
        self.current_class_type = class_type
        for decorator in stmt.decorators:
            if decorator.name == "Entry" and stmt.kind != "struct":
                self._error(decorator, "@Entry 只能修饰 struct 组件")
        for member in stmt.members:
            if isinstance(member, FieldDeclaration):
                self._check_field(member, stmt)
            elif isinstance(member, MethodDeclaration):
                self._check_method(member, stmt)
        self.current_class_type = previous
        self.symbols.pop()

    def _check_field(self, field: FieldDeclaration, owner: ClassDeclaration) -> None:
        decorator_names = [d.name for d in field.decorators]
        for decorator in field.decorators:
            if decorator.name in STATE_DECORATORS:
                if owner.name not in self.structs:
                    self._error(
                        decorator,
                        f"@State 等状态装饰器只能修饰 struct 组件的字段，不能用于 '{owner.name}'",
                    )
                elif owner.name not in self.entries:
                    self._error(
                        decorator,
                        f"@{decorator.name} 变量 '{field.name}' 必须定义在带有 @Entry 的组件中，"
                        f"'{owner.name}' 缺少 @Entry",
                    )
        declared = self._resolve_annotation(field.type_annotation) if field.type_annotation else None
        init_type = self.check(field.init) if field.init is not None else None
        if declared is not None and init_type is not None and not is_assignable(init_type, declared, self.registry):
            self._error(
                field if not field.init else field.init,
                f"类型不匹配：不能将 {init_type} 赋值给 {declared} 类型的字段 '{field.name}'",
            )
        # 字段符号入类作用域
        self.symbols.define(
            Symbol(field.name, SymbolKind.FIELD, type=declared or init_type or UNKNOWN,
                   node=field, decorators=decorator_names, lineno=field.lineno, col=field.col)
        )

    def _check_method(self, method: MethodDeclaration, owner: ClassDeclaration) -> None:
        if method.body is None:
            return  # 接口方法签名
        self.symbols.push("function", f"{owner.name}.{method.name}")
        self._define_params(method.params)
        previous_return = self.current_return
        self.current_return = self._resolve_annotation(method.return_type) if method.return_type else None
        self.check(method.body)
        self.current_return = previous_return
        self.symbols.pop()

    def _check_function(self, stmt: FunctionDeclaration) -> None:
        if stmt.body is None:
            return
        self.symbols.push("function", stmt.name)
        self._define_params(stmt.params)
        previous_return = self.current_return
        self.current_return = self._resolve_annotation(stmt.return_type) if stmt.return_type else None
        self.check(stmt.body)
        self.current_return = previous_return
        self.symbols.pop()

    def _define_params(self, params) -> None:
        for param in params:
            ptype = self._resolve_annotation(param.type_annotation) if param.type_annotation else UNKNOWN
            existing = self.symbols.define(
                Symbol(param.name, SymbolKind.PARAMETER, type=ptype, node=param,
                       lineno=param.lineno, col=param.col)
            )
            if existing is not None:
                self._error(param, f"参数 '{param.name}' 重复定义")
            if param.default is not None:
                default_type = self.check(param.default)
                if not is_assignable(default_type, ptype, self.registry):
                    self._error(param.default, f"参数默认值类型 {default_type} 与声明类型 {ptype} 不匹配")

    # ------------------------------------------------------------ 分发
    def check(self, node):
        if node is None:
            return None
        handler = getattr(self, "_visit_" + type(node).__name__, None)
        if handler is None:
            return None
        result = handler(node)
        if result is not None:
            self.node_types[id(node)] = result
        return result

    # ------------------------------------------------------------ 语句访问器
    def _visit_Block(self, node: Block):
        self.symbols.push("block", "<block>")
        for stmt in node.body:
            self.check(stmt)
        self.symbols.pop()
        return None

    def _visit_ExpressionStatement(self, node: ExpressionStatement):
        self.check(node.expression)
        return None

    def _visit_VariableDeclaration(self, node: VariableDeclaration):
        declared = self._resolve_annotation(node.type_annotation) if node.type_annotation else None
        init_type = self.check(node.init) if node.init is not None else None
        final_type = declared or init_type or UNKNOWN
        if declared is not None and init_type is not None and not is_assignable(init_type, declared, self.registry):
            self._error(
                node.init,
                f"类型不匹配：不能将 {init_type} 赋值给 {declared} 类型的变量 '{node.name}'",
            )
        kind = SymbolKind.CONSTANT if node.kind == "const" else SymbolKind.VARIABLE
        existing = self.symbols.define(
            Symbol(node.name, kind, type=final_type, node=node,
                   lineno=node.lineno, col=node.col, inferred=declared is None)
        )
        if existing is not None:
            self._error(node, f"标识符 '{node.name}' 已在当前作用域中声明")
        return None

    def _check_variable_init(self, node: VariableDeclaration) -> None:
        """全局变量已在声明阶段登记，这里复查初始化表达式并补全类型推断。"""
        declared = self._resolve_annotation(node.type_annotation) if node.type_annotation else None
        if node.init is None:
            return
        init_type = self.check(node.init)
        if declared is not None:
            if not is_assignable(init_type, declared, self.registry):
                self._error(
                    node.init,
                    f"类型不匹配：不能将 {init_type} 赋值给 {declared} 类型的变量 '{node.name}'",
                )
            return
        # 无类型注解时用初始化表达式推断类型（let n = 1; ⇒ n 为 number）
        symbol = self.symbols.global_scope.lookup_local(node.name)
        if symbol is not None and symbol.inferred:
            symbol.type = init_type

    def _visit_IfStatement(self, node: IfStatement):
        self._require_boolean(node.test, "if")
        self.check(node.consequent)
        self.check(node.alternate)
        return None

    def _visit_WhileStatement(self, node: WhileStatement):
        self._require_boolean(node.test, "while")
        self.loop_depth += 1
        self.check(node.body)
        self.loop_depth -= 1
        return None

    def _visit_DoWhileStatement(self, node: DoWhileStatement):
        self.loop_depth += 1
        self.check(node.body)
        self.loop_depth -= 1
        self._require_boolean(node.test, "do-while")
        return None

    def _visit_ForStatement(self, node: ForStatement):
        self.symbols.push("block", "<for>")
        if node.init is not None:
            self.check(node.init)
        if node.test is not None:
            self._require_boolean(node.test, "for")
        if node.update is not None:
            self.check(node.update)
        self.loop_depth += 1
        self.check(node.body)
        self.loop_depth -= 1
        self.symbols.pop()
        return None

    def _visit_ReturnStatement(self, node: ReturnStatement):
        actual = self.check(node.argument) if node.argument is not None else VOID
        if self.current_return is not None and not is_assignable(actual, self.current_return, self.registry):
            self._error(
                node.argument or node,
                f"返回类型不匹配：函数声明返回 {self.current_return}，实际返回 {actual}",
            )
        return None

    def _visit_BreakStatement(self, node: BreakStatement):
        if self.loop_depth == 0:
            self._error(node, "break 只能出现在循环语句中")
        return None

    def _visit_ContinueStatement(self, node: ContinueStatement):
        if self.loop_depth == 0:
            self._error(node, "continue 只能出现在循环语句中")
        return None

    def _require_boolean(self, expr, keyword: str) -> None:
        t = self.check(expr)
        if t is not None and not self._booleanish(t):
            self._error(expr, f"{keyword} 语句的条件必须是 boolean 类型，实际为 {t}")

    @staticmethod
    def _booleanish(t: Type) -> bool:
        return t.kind in (TypeKind.BOOLEAN, TypeKind.ANY, TypeKind.UNKNOWN)

    # ------------------------------------------------------------ 表达式访问器
    def _visit_Literal(self, node: Literal):
        return {
            "number": NUMBER, "string": STRING, "template": STRING,
            "boolean": BOOLEAN, "null": NULL, "undefined": UNDEFINED,
        }.get(node.literal_type, UNKNOWN)

    def _visit_Identifier(self, node: Identifier):
        symbol = self.symbols.resolve(node.name)
        if symbol is None:
            if self.ui_depth > 0:
                return UNKNOWN  # 声明式 UI 的内置组件（Column / Text / Button ...）
            self._error(node, f"未声明的标识符 '{node.name}'")
            return UNKNOWN
        return symbol.type or UNKNOWN

    def _visit_ThisExpression(self, node: ThisExpression):
        if self.current_class_type is None:
            self._error(node, "'this' 只能用于类或组件的成员方法中")
            return UNKNOWN
        return self.current_class_type

    def _visit_SuperExpression(self, node: SuperExpression):
        return self.current_class_type or UNKNOWN

    def _visit_BinaryExpression(self, node: BinaryExpression):
        left = self.check(node.left)
        right = self.check(node.right)
        op = node.operator
        if op in _ARITH_OPS:
            if op == "+" and _same(left, STRING) and _same(right, STRING):
                return STRING
            if _numberish(left) and _numberish(right):
                return NUMBER
            self._error(node, f"运算符 '{op}' 无法作用于 {left} 与 {right}")
            return UNKNOWN
        if op in _RELATIONAL_OPS:
            if left.kind is right.kind and left.kind in (TypeKind.NUMBER, TypeKind.STRING):
                return BOOLEAN
            if _numberish(left) and _numberish(right):
                return BOOLEAN
            self._error(node, f"运算符 '{op}' 要求两侧类型相同（number 或 string），实际为 {left} 与 {right}")
            return UNKNOWN
        if op in _EQUALITY_OPS:
            if is_assignable(left, right, self.registry) or is_assignable(right, left, self.registry):
                return BOOLEAN
            self._error(node, f"运算符 '{op}' 两侧类型不兼容：{left} 与 {right}")
            return BOOLEAN
        if op in _BITWISE_OPS:
            if _numberish(left) and _numberish(right):
                return NUMBER
            self._error(node, f"运算符 '{op}' 要求两侧均为 number，实际为 {left} 与 {right}")
            return UNKNOWN
        if op in ("instanceof", "in"):
            return BOOLEAN
        return UNKNOWN

    def _visit_LogicalExpression(self, node: LogicalExpression):
        left = self.check(node.left)
        right = self.check(node.right)
        if not self._booleanish(left):
            self._error(node.left, f"逻辑运算符 '{node.operator}' 的左操作数必须是 boolean，实际为 {left}")
        if not self._booleanish(right):
            self._error(node.right, f"逻辑运算符 '{node.operator}' 的右操作数必须是 boolean，实际为 {right}")
        return BOOLEAN

    def _visit_UnaryExpression(self, node: UnaryExpression):
        operand = self.check(node.operand)
        op = node.operator
        if op == "!":
            if not self._booleanish(operand):
                self._error(node, f"运算符 '!' 的操作数必须是 boolean，实际为 {operand}")
            return BOOLEAN
        if op in ("-", "+", "~"):
            if not _numberish(operand):
                self._error(node, f"运算符 '{op}' 的操作数必须是 number，实际为 {operand}")
            return NUMBER
        if op == "typeof":
            return STRING
        if op == "void":
            return UNDEFINED
        return operand

    def _visit_UpdateExpression(self, node: UpdateExpression):
        operand = self.check(node.argument)
        if not _numberish(operand):
            self._error(node, f"运算符 '{node.operator}' 只能作用于 number，实际为 {operand}")
        return NUMBER

    def _visit_ConditionalExpression(self, node: ConditionalExpression):
        self._require_boolean(node.test, "三元表达式")
        a = self.check(node.consequent)
        b = self.check(node.alternate)
        if is_assignable(b, a, self.registry):
            return a
        if is_assignable(a, b, self.registry):
            return b
        return union_of([a, b])

    def _visit_AssignmentExpression(self, node: AssignmentExpression):
        self._check_lvalue(node.left)
        left = self.check(node.left)
        right = self.check(node.right)
        if node.operator == "=":
            if not is_assignable(right, left, self.registry):
                self._error(node, f"类型不匹配：不能将 {right} 赋值给 {left}")
        elif node.operator in _COMPOUND_OPS:
            if node.operator == "+=" and _same(left, STRING) and _same(right, STRING):
                return STRING
            if not (_numberish(left) and _numberish(right)):
                self._error(node, f"复合赋值 '{node.operator}' 要求两侧均为 number，实际为 {left} 与 {right}")
        return left

    def _check_lvalue(self, node) -> None:
        if isinstance(node, Identifier):
            symbol = self.symbols.resolve(node.name)
            if symbol is not None and symbol.kind is SymbolKind.CONSTANT:
                self._error(node, f"不能给常量 '{node.name}' 赋值")
        elif isinstance(node, MemberExpression):
            return
        else:
            self._error(node, "非法的赋值目标")

    def _visit_CallExpression(self, node: CallExpression):
        arg_types = [self.check(a) for a in node.arguments]
        callee_type = self._resolve_callee(node.callee)
        if callee_type is None:
            return UNKNOWN
        if callee_type.kind is TypeKind.FUNCTION:
            self._check_arguments(node, callee_type, arg_types)
            return callee_type.return_type or UNKNOWN
        if callee_type.kind in (TypeKind.UNKNOWN, TypeKind.ANY):
            return UNKNOWN  # 无法判定的类型（例如声明式 UI 的链式调用）不报错
        self._error(node, f"'{_callee_name(node.callee)}' 不是可调用的函数")
        return UNKNOWN

    def _check_arguments(self, node, func_type: Type, arg_types: list) -> None:
        expected = func_type.param_types
        if len(arg_types) < len(expected):
            self._error(
                node,
                f"参数个数不足：需要 {len(expected)} 个参数，实际传入 {len(arg_types)} 个",
            )
            return
        if len(arg_types) > len(expected):
            self._error(
                node,
                f"参数个数过多：需要 {len(expected)} 个参数，实际传入 {len(arg_types)} 个",
            )
            return
        for i, (actual, formal) in enumerate(zip(arg_types, expected)):
            if not is_assignable(actual, formal, self.registry):
                self._error(
                    node.arguments[i],
                    f"第 {i + 1} 个参数类型不匹配：期望 {formal}，实际 {actual}",
                )

    def _resolve_callee(self, callee) -> Type | None:
        if isinstance(callee, Identifier):
            symbol = self.symbols.resolve(callee.name)
            if symbol is None:
                if self.ui_depth > 0:
                    return None  # 内置 UI 组件，不参与类型检查
                self._error(callee, f"未声明的函数 '{callee.name}'")
                return None
            return symbol.type
        if isinstance(callee, MemberExpression):
            return self._visit_MemberExpression(callee)
        return self.check(callee)

    def _visit_NewExpression(self, node: NewExpression):
        target = self._resolve_type_name(node.callee)
        if target is None:
            return UNKNOWN
        if target.kind not in (TypeKind.CLASS, TypeKind.INTERFACE):
            self._error(node, f"'{target}' 不能被 new 实例化")
            return UNKNOWN
        ctor = self.registry.member(target, "constructor")
        if ctor is not None and ctor.type.kind is TypeKind.FUNCTION:
            arg_types = [self.check(a) for a in node.arguments]
            self._check_arguments(node, ctor.type, arg_types)
        return target

    def _resolve_type_name(self, callee) -> Type | None:
        if isinstance(callee, Identifier):
            symbol = self.symbols.resolve(callee.name)
            if symbol is None:
                self._error(callee, f"未声明的类型 '{callee.name}'")
                return None
            return symbol.type
        if isinstance(callee, MemberExpression):
            return self._visit_MemberExpression(callee)
        return UNKNOWN

    def _visit_MemberExpression(self, node: MemberExpression):
        obj_type = self.check(node.object)
        if node.computed:
            self.check(node.property)
            if obj_type.kind is TypeKind.ARRAY:
                return obj_type.element or UNKNOWN
            return UNKNOWN
        name = node.property.name if isinstance(node.property, Identifier) else ""
        if obj_type.kind in (TypeKind.UNKNOWN, TypeKind.ANY):
            return UNKNOWN
        if obj_type.kind is TypeKind.ARRAY and name == "length":
            return NUMBER
        info = self.registry.member(obj_type, name)
        if info is None:
            if self.ui_depth > 0:
                return UNKNOWN  # 声明式 UI 的链式调用（.fontSize / .onClick ...）
            self._error(node, f"类型 '{obj_type}' 上不存在成员 '{name}'")
            return UNKNOWN
        if info.visibility in ("private", "protected") and not self._accessible(info):
            self._error(node, f"成员 '{name}' 是 {info.visibility} 的，不能在类外部访问")
        return info.type

    def _accessible(self, info: MemberInfo) -> bool:
        """判断 private / protected 成员是否可在当前位置访问。

        规则：只有当该成员定义于当前所处的类（或其基类）时才可访问，
        即 ``this.privateField`` 合法，访问其它对象的私有成员非法。
        """
        if self.current_class_type is None:
            return False
        return self.registry.member(self.current_class_type, info.name) is info

    def _visit_ArrayLiteral(self, node: ArrayLiteral):
        element_types = [self.check(e) for e in node.elements]
        if not element_types:
            return array_of(UNKNOWN)
        first = element_types[0]
        for t in element_types[1:]:
            if not is_assignable(t, first, self.registry):
                self._error(node, f"数组元素类型不一致：{t} 与 {first}")
                return array_of(ANY)
        return array_of(first)

    def _visit_ObjectLiteral(self, node: ObjectLiteral):
        for prop in node.properties:
            self.check(prop.value)
        return Type(TypeKind.CLASS, "<object>")

    def _visit_ArrowFunctionExpression(self, node: ArrowFunctionExpression):
        self.symbols.push("function", "<arrow>")
        self._define_params(node.params)
        previous_return = self.current_return
        self.current_return = None
        result = self.check(node.body) if node.is_expression else None
        if not node.is_expression:
            self.check(node.body)
        self.current_return = previous_return
        self.symbols.pop()
        param_types = [self._resolve_annotation(p.type_annotation) for p in node.params]
        return function_type(param_types, result or VOID)

    def _visit_UiContainer(self, node: UiContainer):
        self.ui_depth += 1
        for arg in node.arguments:
            self.check(arg)
        for child in node.children:
            self.check(child)
        self.ui_depth -= 1
        return VOID

    # ------------------------------------------------------------ 类型注解
    def _resolve_annotation(self, anno: TypeAnnotation | None) -> Type:
        if anno is None:
            return UNKNOWN
        if anno.name == "Array" and anno.type_args:
            return array_of(self._resolve_annotation(anno.type_args[0]))
        base = self.registry.resolve(anno.name)
        if base is None:
            self._error(anno, f"未知的类型 '{anno.name}'")
            base = UNKNOWN
        if anno.type_args:
            return base
        if anno.is_array:
            return array_of(base)
        return base


def _visibility(modifiers: list) -> str:
    for mod in modifiers:
        if mod in ("private", "protected", "public"):
            return mod
    return "public"


def _same(t: Type, other: Type) -> bool:
    return t is other or (t.name and t.name == other.name)


def _numberish(t: Type) -> bool:
    return t.kind in (TypeKind.NUMBER, TypeKind.ANY, TypeKind.UNKNOWN)


def _callee_name(callee) -> str:
    if isinstance(callee, Identifier):
        return callee.name
    if isinstance(callee, MemberExpression) and isinstance(callee.property, Identifier):
        return callee.property.name
    return "<expression>"


def analyze(program: Program, filename: str = "<source>") -> tuple[list[Diagnostic], SemanticAnalyzer]:
    """便捷函数：返回 ``(errors, analyzer)``。"""
    analyzer = SemanticAnalyzer(filename)
    errors = analyzer.analyze(program)
    return errors, analyzer