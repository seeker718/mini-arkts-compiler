"""AST -> 三地址码 IR 的转换（实验三）。

输入：实验二语义分析后的 AST（可通过 analyzer.node_types 取得各节点的类型）。
输出：:class:`compiler.ir.IRModule`。

映射规则：
    * 顶层 function          -> IRFunction
    * 类/结构体的方法、构造器 -> IRFunction（名字形如 ``Person.greet``，方法带隐含的 ``%this``）
    * 类字段、全局变量        -> IRModule.globals
    * if / while / for       -> br / jmp + 基本块；分支汇合处用 phi 合并变量版本
    * 装饰器与 build() 声明式 UI 不参与计算型 IR 生成，直接跳过

SSA 模拟：变量每次被赋值都会产生新版本（``%x`` -> ``%x.1`` -> ``%x.2``），
控制流汇合处为「在不同路径上取值不同」的变量插入 ``phi`` 指令。
"""

from __future__ import annotations

from . import ir
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
    ThisExpression,
    UiContainer,
    UnaryExpression,
    UpdateExpression,
    VariableDeclaration,
    WhileStatement,
)

_BINOP_MAP = {
    "+": ir.OP_ADD, "-": ir.OP_SUB, "*": ir.OP_MUL, "/": ir.OP_DIV, "%": ir.OP_MOD,
    "<": ir.OP_LT, ">": ir.OP_GT, "<=": ir.OP_LE, ">=": ir.OP_GE,
    "==": ir.OP_EQ, "!=": ir.OP_NE, "===": ir.OP_EQ, "!==": ir.OP_NE,
    "&": ir.OP_BAND, "|": ir.OP_BOR, "^": ir.OP_BXOR,
    "<<": ir.OP_SHL, ">>": ir.OP_SHR, ">>>": ir.OP_SHR,
}
_COMPOUND_MAP = {
    "+=": ir.OP_ADD, "-=": ir.OP_SUB, "*=": ir.OP_MUL, "/=": ir.OP_DIV, "%=": ir.OP_MOD,
}
_UI_METHODS = {"build", "onClick", "onAppear", "onDisappear"}
_SKIP_DECORATORS = {"Builder", "BuilderParam", "Styles", "Extend"}
_PRIMITIVE_NAMES = {"number", "string", "boolean", "array", "void", "<unknown>", ""}


class IRGenerator:
    def __init__(self, analyzer=None, filename: str = "<source>") -> None:
        self.analyzer = analyzer
        self.filename = filename
        self.module = ir.IRModule(name="mini_arkts_module")
        self.func: ir.IRFunction | None = None
        self.block: ir.IRBasicBlock | None = None
        self.env: dict[str, str] = {}
        self.versions: dict[str, int] = {}
        self._temp = 0
        self._label = 0
        self.loop_break: str | None = None
        self.loop_continue: str | None = None

    # ------------------------------------------------------------ 顶层
    def generate(self, program: Program) -> ir.IRModule:
        for stmt in program.body:
            if isinstance(stmt, FunctionDeclaration):
                self._gen_function(stmt)
            elif isinstance(stmt, ClassDeclaration):
                self._gen_class(stmt)
            elif isinstance(stmt, VariableDeclaration):
                self.module.globals.append(
                    (f"@{self._sanitize(stmt.name)}", self._decl_type(stmt))
                )
        return self.module

    def _gen_class(self, node: ClassDeclaration) -> None:
        if node.kind == "interface":
            return  # 接口只有方法签名、没有实现，不参与计算型 IR 生成
        for member in node.members:
            if isinstance(member, MethodDeclaration):
                if member.name in _UI_METHODS:
                    continue
                if any(d.name in _SKIP_DECORATORS for d in member.decorators):
                    continue
                self._gen_function(member, owner=node.name)
            elif isinstance(member, FieldDeclaration):
                self.module.globals.append(
                    (f"@{node.name}.{self._sanitize(member.name)}", self._decl_type(member))
                )

    # ------------------------------------------------------------ 函数
    def _gen_function(self, node, owner: str | None = None) -> None:
        name = f"{owner}.{node.name}" if owner else node.name
        func = ir.IRFunction(
            name=name,
            return_type=self._decl_type(node),
            is_method=owner is not None,
            owner=owner,
        )

        self.func = func
        self.env = {}
        self.versions = {}
        self._temp = 0
        self._label = 0

        for i, param in enumerate(node.params):
            pname = f"%p{i}_{self._sanitize(param.name)}"
            ptype = self._type_of(param.type_annotation)
            func.params.append(pname)
            func.param_types.append(ptype)
            func.local_types[pname] = ptype
            self.env[param.name] = pname

        if owner is not None:
            self.env["this"] = "%this"
            func.local_types["%this"] = owner

        self._start_block("entry")
        if node.body is not None:            # 接口 / 抽象方法可能没有方法体
            self._stmt_list(node.body.body)
        self._ensure_return()

        self.func = None
        self.block = None
        self.module.functions.append(func)

    def _ensure_return(self) -> None:
        if not self.func.blocks:
            self._start_block("entry")
        last = self.func.blocks[-1]
        if last.instructions and last.instructions[-1].op in (ir.OP_RET, ir.OP_JMP, ir.OP_BR):
            return
        self._emit(ir.OP_RET, args=[])

    # ------------------------------------------------------------ 基础设施
    def _start_block(self, label: str) -> ir.IRBasicBlock:
        block = ir.IRBasicBlock(label=label)
        self.func.blocks.append(block)
        self.block = block
        return block

    def _emit(self, op: str, dst: str | None = None, args=None, lineno: int = 0):
        ins = ir.IRInstruction(
            op=op, dst=dst, args=list(args or []),
            device=self.func.device_id if self.func else 0, lineno=lineno,
        )
        self.block.instructions.append(ins)
        return ins

    def _new_temp(self) -> str:
        self._temp += 1
        return f"%t{self._temp}"

    def _new_label(self, base: str) -> str:
        self._label += 1
        return f"{base}.{self._label}"

    @staticmethod
    def _sanitize(name: str) -> str:
        return name.replace(".", "_").replace("%", "").replace("@", "")

    def _define(self, name: str, value: str, type_name: str, lineno: int = 0) -> str:
        key = self._sanitize(name)
        count = self.versions.get(name, 0) + 1
        self.versions[name] = count
        ir_name = f"%{key}" if count == 1 else f"%{key}.{count}"
        self.env[name] = ir_name
        self.func.local_types[ir_name] = type_name
        self._emit(ir.OP_ASSIGN, dst=ir_name, args=[value], lineno=lineno)
        return ir_name

    def _ref(self, name: str) -> str:
        if name in self.env:
            return self.env[name]
        return f"%{self._sanitize(name)}"

    # ------------------------------------------------------------ 类型辅助
    def _decl_type(self, node) -> str:
        anno = getattr(node, "type_annotation", None)
        if anno is None:
            anno = getattr(node, "return_type", None)
        return self._type_of(anno)

    def _type_of(self, anno) -> str:
        if anno is None:
            return "number"
        if getattr(anno, "is_array", False) or anno.name == "Array":
            return "array"
        return anno.name

    def _type_of_expr(self, node) -> str:
        if self.analyzer is not None:
            name = str(self.analyzer.type_of(node))
            if name and name not in _PRIMITIVE_NAMES:
                return name
            if name in ("number", "string", "boolean"):
                return name
        return "number"

    # ------------------------------------------------------------ 语句分发
    def _stmt_list(self, statements) -> None:
        for stmt in statements:
            self._stmt(stmt)

    def _stmt(self, node) -> None:
        if node is None:
            return
        method = getattr(self, "_s_" + type(node).__name__, None)
        if method is not None:
            method(node)

    # ------------------------------------------------------------ 语句
    def _s_VariableDeclaration(self, node: VariableDeclaration) -> None:
        if node.init is not None:
            value = self._expr(node.init)
        else:
            value = _default_value(self._decl_type(node))
        self._define(node.name, value, self._decl_type(node), node.lineno)

    def _s_ExpressionStatement(self, node: ExpressionStatement) -> None:
        self._expr(node.expression)

    def _s_Block(self, node: Block) -> None:
        self._stmt_list(node.body)

    def _s_IfStatement(self, node: IfStatement) -> None:
        cond = self._expr(node.test)
        then_label = self._new_label("if.then")
        else_label = self._new_label("if.else")
        end_label = self._new_label("if.end")
        self._emit(ir.OP_BR, args=[cond, then_label, else_label])

        before = dict(self.env)

        self._start_block(then_label)
        self.env = dict(before)
        self._stmt(node.consequent)
        self._emit(ir.OP_JMP, args=[end_label])
        then_env = dict(self.env)
        then_end = self.block.label

        self._start_block(else_label)
        self.env = dict(before)
        if node.alternate is not None:
            self._stmt(node.alternate)
        self._emit(ir.OP_JMP, args=[end_label])
        else_env = dict(self.env)
        else_end = self.block.label

        self._start_block(end_label)
        self.env = dict(before)
        self._merge_phi(before, then_env, else_env, then_end, else_end)

    def _merge_phi(self, before, then_env, else_env, then_end, else_end) -> None:
        for name in sorted(set(then_env) | set(else_env)):
            then_val = then_env.get(name, before.get(name))
            else_val = else_env.get(name, before.get(name))
            if then_val is None or else_val is None:
                continue
            if then_val == else_val:
                self.env[name] = then_val
                continue
            count = self.versions.get(name, 0) + 1
            self.versions[name] = count
            key = self._sanitize(name)
            phi_name = f"%{key}" if count == 1 else f"%{key}.{count}"
            self.env[name] = phi_name
            self.func.local_types[phi_name] = self.func.local_types.get(then_val, "number")
            self._emit(ir.OP_PHI, dst=phi_name,
                       args=[(then_val, then_end), (else_val, else_end)])

    def _s_WhileStatement(self, node: WhileStatement) -> None:
        cond_label = self._new_label("while.cond")
        body_label = self._new_label("while.body")
        end_label = self._new_label("while.end")
        self._emit(ir.OP_JMP, args=[cond_label])
        self._start_block(cond_label)
        cond = self._expr(node.test)
        self._emit(ir.OP_BR, args=[cond, body_label, end_label])
        self._start_block(body_label)
        old_break, old_continue = self.loop_break, self.loop_continue
        self.loop_break, self.loop_continue = end_label, cond_label
        self._stmt(node.body)
        self._emit(ir.OP_JMP, args=[cond_label])
        self.loop_break, self.loop_continue = old_break, old_continue
        self._start_block(end_label)

    def _s_DoWhileStatement(self, node: DoWhileStatement) -> None:
        body_label = self._new_label("do.body")
        cond_label = self._new_label("do.cond")
        end_label = self._new_label("do.end")
        self._emit(ir.OP_JMP, args=[body_label])
        self._start_block(body_label)
        old_break, old_continue = self.loop_break, self.loop_continue
        self.loop_break, self.loop_continue = end_label, cond_label
        self._stmt(node.body)
        self._emit(ir.OP_JMP, args=[cond_label])
        self.loop_break, self.loop_continue = old_break, old_continue
        self._start_block(cond_label)
        cond = self._expr(node.test)
        self._emit(ir.OP_BR, args=[cond, body_label, end_label])
        self._start_block(end_label)

    def _s_ForStatement(self, node: ForStatement) -> None:
        if node.init is not None:
            self._stmt(node.init)
        cond_label = self._new_label("for.cond")
        body_label = self._new_label("for.body")
        update_label = self._new_label("for.update")
        end_label = self._new_label("for.end")
        self._emit(ir.OP_JMP, args=[cond_label])

        self._start_block(cond_label)
        cond = self._expr(node.test) if node.test is not None else "true"
        self._emit(ir.OP_BR, args=[cond, body_label, end_label])

        self._start_block(body_label)
        old_break, old_continue = self.loop_break, self.loop_continue
        self.loop_break, self.loop_continue = end_label, update_label
        self._stmt(node.body)
        self._emit(ir.OP_JMP, args=[update_label])
        self.loop_break, self.loop_continue = old_break, old_continue

        self._start_block(update_label)
        if node.update is not None:
            self._expr(node.update)
        self._emit(ir.OP_JMP, args=[cond_label])
        self._start_block(end_label)

    def _s_ReturnStatement(self, node: ReturnStatement) -> None:
        value = self._expr(node.argument) if node.argument is not None else None
        self._emit(ir.OP_RET, args=[value] if value else [])

    def _s_BreakStatement(self, node: BreakStatement) -> None:
        if self.loop_break:
            self._emit(ir.OP_JMP, args=[self.loop_break])

    def _s_ContinueStatement(self, node: ContinueStatement) -> None:
        if self.loop_continue:
            self._emit(ir.OP_JMP, args=[self.loop_continue])

    def _s_UiContainer(self, node: UiContainer) -> None:
        return

    # ------------------------------------------------------------ 表达式分发
    def _expr(self, node) -> str:
        if node is None:
            return "0"
        method = getattr(self, "_e_" + type(node).__name__, None)
        if method is not None:
            return method(node)
        return "0"

    def _e_Literal(self, node: Literal) -> str:
        kind = node.literal_type
        if kind == "number":
            return _number_text(node.value)
        if kind == "string":
            return _string_text(node.value)
        if kind == "template":
            return _string_text(node.raw)
        if kind == "boolean":
            return "true" if node.value else "false"
        return "0"

    def _e_Identifier(self, node: Identifier) -> str:
        return self._ref(node.name)

    def _e_ThisExpression(self, node: ThisExpression) -> str:
        return "%this"

    def _e_BinaryExpression(self, node: BinaryExpression) -> str:
        left = self._expr(node.left)
        right = self._expr(node.right)
        op = _BINOP_MAP.get(node.operator, ir.OP_ADD)
        temp = self._new_temp()
        self._emit(op, dst=temp, args=[left, right], lineno=node.lineno)
        return temp

    def _e_LogicalExpression(self, node: LogicalExpression) -> str:
        left = self._expr(node.left)
        right = self._expr(node.right)
        op = ir.OP_LAND if node.operator == "&&" else ir.OP_LOR
        temp = self._new_temp()
        self._emit(op, dst=temp, args=[left, right], lineno=node.lineno)
        return temp

    def _e_UnaryExpression(self, node: UnaryExpression) -> str:
        operand = self._expr(node.operand)
        op = {"-": ir.OP_NEG, "!": ir.OP_NOT, "~": ir.OP_BNOT}.get(node.operator)
        if op is None:
            return operand
        temp = self._new_temp()
        self._emit(op, dst=temp, args=[operand], lineno=node.lineno)
        return temp

    def _e_UpdateExpression(self, node: UpdateExpression) -> str:
        old = self._expr(node.argument)
        op = ir.OP_ADD if node.operator == "++" else ir.OP_SUB
        temp = self._new_temp()
        self._emit(op, dst=temp, args=[old, "1"], lineno=node.lineno)
        self._assign_to(node.argument, temp)
        return temp if node.prefix else old

    def _e_AssignmentExpression(self, node: AssignmentExpression) -> str:
        value = self._expr(node.right)
        if node.operator in _COMPOUND_MAP:
            current = self._expr(node.left)
            temp = self._new_temp()
            self._emit(_COMPOUND_MAP[node.operator], dst=temp, args=[current, value],
                       lineno=node.lineno)
            value = temp
        return self._assign_to(node.left, value)

    def _assign_to(self, target, value: str) -> str:
        if isinstance(target, Identifier):
            return self._define(target.name, value, self._type_of_expr(target), target.lineno)
        if isinstance(target, MemberExpression):
            obj = self._expr(target.object)
            if target.computed:
                index = self._expr(target.property)
                self._emit(ir.OP_ARRAY_STORE, args=[obj, index, value])
            else:
                name = target.property.name if isinstance(target.property, Identifier) else "?"
                self._emit(ir.OP_FIELD_STORE, args=[obj, name, value])
        return value

    def _e_CallExpression(self, node: CallExpression) -> str:
        callee_name, receiver = self._resolve_callee(node.callee)
        args = []
        if receiver is not None:
            args.append(receiver)
        args.extend(self._expr(a) for a in node.arguments)
        temp = self._new_temp()
        temp_type = self._type_of_expr(node)
        self.func.local_types[temp] = temp_type
        self._emit(ir.OP_CALL, dst=temp, args=[callee_name] + args, lineno=node.lineno)
        return temp

    def _resolve_callee(self, callee):
        if isinstance(callee, Identifier):
            return callee.name, None
        if isinstance(callee, MemberExpression) and not callee.computed \
                and isinstance(callee.property, Identifier):
            prop = callee.property.name
            owner = self._type_of_expr(callee.object)
            if owner not in _PRIMITIVE_NAMES:
                return f"{owner}.{prop}", self._expr(callee.object)
            return prop, None
        return "<expr>", None

    def _e_MemberExpression(self, node: MemberExpression) -> str:
        obj = self._expr(node.object)
        temp = self._new_temp()
        if node.computed:
            index = self._expr(node.property)
            self._emit(ir.OP_ARRAY_LOAD, dst=temp, args=[obj, index])
        else:
            name = node.property.name if isinstance(node.property, Identifier) else "?"
            self._emit(ir.OP_FIELD_LOAD, dst=temp, args=[obj, name])
        self.func.local_types[temp] = self._type_of_expr(node)
        return temp

    def _e_NewExpression(self, node: NewExpression) -> str:
        cls = node.callee.name if isinstance(node.callee, Identifier) else "Object"
        temp = self._new_temp()
        self.func.local_types[temp] = cls
        self._emit(ir.OP_NEW, dst=temp, args=[cls])
        for arg in node.arguments:
            self._expr(arg)
        return temp

    def _e_ArrayLiteral(self, node: ArrayLiteral) -> str:
        temp = self._new_temp()
        self.func.local_types[temp] = "array"
        self._emit(ir.OP_ARRAY_NEW, dst=temp, args=[str(len(node.elements))])
        for i, element in enumerate(node.elements):
            value = self._expr(element)
            self._emit(ir.OP_ARRAY_STORE, args=[temp, str(i), value])
        return temp

    def _e_ConditionalExpression(self, node: ConditionalExpression) -> str:
        cond = self._expr(node.test)
        then_label = self._new_label("cond.then")
        else_label = self._new_label("cond.else")
        end_label = self._new_label("cond.end")
        self._emit(ir.OP_BR, args=[cond, then_label, else_label])
        before = dict(self.env)

        self._start_block(then_label)
        self.env = dict(before)
        then_value = self._expr(node.consequent)
        self._emit(ir.OP_JMP, args=[end_label])
        then_end = self.block.label

        self._start_block(else_label)
        self.env = dict(before)
        else_value = self._expr(node.alternate)
        self._emit(ir.OP_JMP, args=[end_label])
        else_end = self.block.label

        self._start_block(end_label)
        self.env = dict(before)
        temp = self._new_temp()
        self._emit(ir.OP_PHI, dst=temp,
                   args=[(then_value, then_end), (else_value, else_end)])
        return temp

    def _e_ArrowFunctionExpression(self, node: ArrowFunctionExpression) -> str:
        return "0"

    def _e_ObjectLiteral(self, node: ObjectLiteral) -> str:
        return "0"


# ---------------------------------------------------------------- 字面量文本
def _number_text(value) -> str:
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return repr(value)
    return str(value)


def _string_text(value) -> str:
    body = str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{body}"'


def _default_value(type_name: str) -> str:
    if type_name == "string":
        return '""'
    if type_name == "boolean":
        return "false"
    return "0"


def generate(program: Program, analyzer=None, filename: str = "<source>") -> ir.IRModule:
    """便捷函数：AST -> IRModule。"""
    return IRGenerator(analyzer, filename).generate(program)