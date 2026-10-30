"""IR 级 AOT 优化 Pass（实验四）。

实现两种经典优化技术：

1. **常量折叠（Constant Folding）+ 常量传播（Constant Propagation）**
   ``%t = mul 3, 4`` 直接在编译期算成 12，并把结果代入后续使用点；
2. **死代码消除（Dead Code Elimination）**
   * 恒真 / 恒假的条件分支简化为无条件跳转；
   * 从入口做可达性分析，删除不可达基本块；
   * 删除「结果从未被使用且无副作用」的纯计算指令。

优化在 IR 生成之后运行，可迭代多轮以便折叠后暴露出新的死代码。
"""

from __future__ import annotations

from . import ir

# 无副作用的操作码：结果未被使用时可以安全删除
_PURE_OPS = ir.BINARY_OPS | {
    ir.OP_ASSIGN, ir.OP_NEG, ir.OP_NOT, ir.OP_BNOT, ir.OP_FIELD_LOAD, ir.OP_ARRAY_LOAD,
}


class Optimizer:
    """对 IRModule 施加优化，并统计优化效果。"""

    def __init__(self, module: ir.IRModule) -> None:
        self.module = module
        self.stats = {
            "before": 0,
            "after": 0,
            "constant_folded": 0,
            "branch_simplified": 0,
            "block_removed": 0,
            "instruction_removed": 0,
        }

    # ------------------------------------------------------------ 对外接口
    def run(self, rounds: int = 3) -> dict:
        self.stats["before"] = self._count()
        for _ in range(rounds):
            changed = False
            for func in self.module.functions:
                changed |= self._fold_constants(func) > 0
                changed |= self._eliminate_dead_code(func) > 0
            if not changed:
                break
        self.stats["after"] = self._count()
        return dict(self.stats)

    def _count(self) -> int:
        return sum(f.instruction_count() for f in self.module.functions)

    # ------------------------------------------------------------ 常量折叠
    def _fold_constants(self, func: ir.IRFunction) -> int:
        constants: dict[str, str] = {}
        folded = 0
        for block in func.blocks:
            for index, ins in enumerate(block.instructions):
                ins.args = _substitute(ins.args, constants)
                value = _try_fold(ins)
                if value is None:
                    continue
                if ins.dst:
                    constants[ins.dst] = value
                block.instructions[index] = ir.IRInstruction(
                    op=ir.OP_ASSIGN, dst=ins.dst, args=[value],
                    device=ins.device, lineno=ins.lineno,
                )
                folded += 1
        self.stats["constant_folded"] += folded
        return folded

    # ------------------------------------------------------------ 死代码消除
    def _eliminate_dead_code(self, func: ir.IRFunction) -> int:
        removed = self._simplify_branches(func)
        removed += self._remove_unreachable(func)
        removed += self._remove_unused(func)
        return removed

    def _simplify_branches(self, func: ir.IRFunction) -> int:
        """把条件恒为常量的 br 简化为 jmp。"""
        count = 0
        for block in func.blocks:
            for index, ins in enumerate(block.instructions):
                if ins.op != ir.OP_BR:
                    continue
                cond = _const_bool(ins.args[0])
                if cond is None:
                    continue
                target = ins.args[1] if cond else ins.args[2]
                block.instructions[index] = ir.IRInstruction(
                    op=ir.OP_JMP, args=[target], device=ins.device,
                )
                count += 1
        self.stats["branch_simplified"] += count
        return count

    def _remove_unreachable(self, func: ir.IRFunction) -> int:
        """从 entry 出发做可达性分析，删除不可达基本块。

        注意：φ 的「前驱」只是它记录的控制流来源，可达性必须由 br / jmp 决定，
        因此这里不把 φ 的前驱算作可达；删除块之后再清理 φ 中失效的入边。
        """
        if not func.blocks:
            return 0
        labels = {b.label for b in func.blocks}
        by_label = {b.label: b for b in func.blocks}

        reachable: set[str] = set()
        stack = [func.blocks[0].label]
        while stack:
            label = stack.pop()
            if label in reachable or label not in labels:
                continue
            reachable.add(label)
            for ins in by_label[label].instructions:
                if ins.op == ir.OP_JMP:
                    stack.append(ins.args[0])
                elif ins.op == ir.OP_BR:
                    stack.append(ins.args[1])
                    stack.append(ins.args[2])

        removed = len(func.blocks) - len(reachable)
        if removed:
            func.blocks = [b for b in func.blocks if b.label in reachable]
            self._prune_phi(func, reachable)
        self.stats["block_removed"] += removed
        return removed

    def _prune_phi(self, func: ir.IRFunction, reachable: set) -> None:
        """删除指向不可达前驱的 φ 入边；只剩一个入边时退化为普通赋值。"""
        for block in func.blocks:
            for index, ins in enumerate(block.instructions):
                if ins.op != ir.OP_PHI:
                    continue
                kept = [(value, label) for value, label in ins.args if label in reachable]
                if len(kept) == 1:
                    block.instructions[index] = ir.IRInstruction(
                        op=ir.OP_ASSIGN, dst=ins.dst, args=[kept[0][0]], device=ins.device,
                    )
                elif kept:
                    ins.args = kept

    def _remove_unused(self, func: ir.IRFunction) -> int:
        """删除结果未被使用且无副作用的指令。"""
        used: set[str] = set()
        for block in func.blocks:
            for ins in block.instructions:
                if ins.op == ir.OP_RET and ins.args:
                    used.add(ins.args[0])
                for arg in ins.args:
                    if isinstance(arg, tuple):
                        used.add(arg[0])
                    elif isinstance(arg, str) and arg.startswith("%"):
                        used.add(arg)

        removed = 0
        for block in func.blocks:
            kept: list[ir.IRInstruction] = []
            for ins in block.instructions:
                if ins.dst and ins.dst not in used and ins.op in _PURE_OPS:
                    removed += 1
                    continue
                kept.append(ins)
            block.instructions = kept
        self.stats["instruction_removed"] += removed
        return removed


# ---------------------------------------------------------------- 辅助
def _substitute(args, constants: dict[str, str]) -> list:
    """把操作数中的已知常量替换进去（含 φ 的 (值, 前驱) 二元组）。"""
    result = []
    for arg in args:
        if isinstance(arg, tuple):
            value, label = arg
            result.append((constants.get(value, value), label))
        elif isinstance(arg, str) and arg in constants:
            result.append(constants[arg])
        else:
            result.append(arg)
    return result


def _try_fold(ins: ir.IRInstruction) -> str | None:
    """若指令所有操作数都是常量，则求值并返回常量文本。"""
    if ins.op in ir.BINARY_OPS and len(ins.args) >= 2:
        left, right = ins.args[0], ins.args[1]
        if _is_const(left) and _is_const(right):
            return _eval_binary(ins.op, left, right)
    if ins.op in (ir.OP_NEG, ir.OP_NOT, ir.OP_BNOT) and ins.args:
        operand = ins.args[0]
        if _is_const(operand):
            return _eval_unary(ins.op, operand)
    if ins.op == ir.OP_ASSIGN and ins.args and _is_const(ins.args[0]):
        return ins.args[0]
    return None


def _is_string(text) -> bool:
    return isinstance(text, str) and len(text) >= 2 and text[0] == '"' and text[-1] == '"'


def _is_number(text) -> bool:
    if not isinstance(text, str):
        return False
    try:
        float(text)
        return True
    except ValueError:
        return False


def _is_const(text) -> bool:
    if not isinstance(text, str):
        return False
    return _is_number(text) or _is_string(text) or text in ("true", "false")


def _const_bool(text):
    if text == "true":
        return True
    if text == "false":
        return False
    if _is_number(text):
        return float(text) != 0.0
    return None


def _fmt(value) -> str:
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _num(text: str) -> float:
    return float(text)


def _eval_binary(op: str, left: str, right: str) -> str | None:
    # 字符串拼接
    if op == ir.OP_ADD and _is_string(left) and _is_string(right):
        return '"' + left[1:-1] + right[1:-1] + '"'

    a = _num(left) if _is_number(left) else None
    b = _num(right) if _is_number(right) else None

    if op in (ir.OP_EQ, ir.OP_NE):
        if left == right:
            return "true" if op == ir.OP_EQ else "false"
        if a is None or b is None:
            return None
        same = a == b
        return "true" if same == (op == ir.OP_EQ) else "false"

    if a is None or b is None:
        return None

    try:
        if op == ir.OP_ADD:
            return _fmt(a + b)
        if op == ir.OP_SUB:
            return _fmt(a - b)
        if op == ir.OP_MUL:
            return _fmt(a * b)
        if op == ir.OP_DIV:
            return _fmt(a / b) if b != 0 else None
        if op == ir.OP_MOD:
            return _fmt(a % b) if b != 0 else None
        if op == ir.OP_LT:
            return _fmt(a < b)
        if op == ir.OP_GT:
            return _fmt(a > b)
        if op == ir.OP_LE:
            return _fmt(a <= b)
        if op == ir.OP_GE:
            return _fmt(a >= b)
        if op == ir.OP_LAND:
            return _fmt(bool(a) and bool(b))
        if op == ir.OP_LOR:
            return _fmt(bool(a) or bool(b))
        if op == ir.OP_BAND:
            return _fmt(int(a) & int(b))
        if op == ir.OP_BOR:
            return _fmt(int(a) | int(b))
        if op == ir.OP_BXOR:
            return _fmt(int(a) ^ int(b))
        if op == ir.OP_SHL:
            return _fmt(int(a) << int(b))
        if op == ir.OP_SHR:
            return _fmt(int(a) >> int(b))
    except (ZeroDivisionError, OverflowError, ValueError):
        return None
    return None


def _eval_unary(op: str, operand: str) -> str | None:
    if op == ir.OP_NEG and _is_number(operand):
        return _fmt(-_num(operand))
    if op == ir.OP_NOT:
        value = _const_bool(operand)
        return None if value is None else _fmt(not value)
    if op == ir.OP_BNOT and _is_number(operand):
        return _fmt(~int(_num(operand)))
    return None


def optimize(module: ir.IRModule, rounds: int = 3) -> dict:
    """便捷函数：对模块施加优化并返回统计。"""
    return Optimizer(module).run(rounds)


def diff_text(before: ir.IRModule, after: ir.IRModule) -> str:
    """生成优化前后的 IR 对比文本（按函数列出指令数变化）。"""
    lines = ["优化前后对比", "-" * 52,
             f"{'函数':<20}{'优化前':>8}{'优化后':>8}{'减少':>8}"]
    total_before = total_after = 0
    for func_before in before.functions:
        func_after = after.function(func_before.name)
        n_before = func_before.instruction_count()
        n_after = func_after.instruction_count() if func_after else 0
        total_before += n_before
        total_after += n_after
        lines.append(f"{func_before.name:<20}{n_before:>8}{n_after:>8}{n_before - n_after:>8}")
    lines.append("-" * 52)
    lines.append(f"{'合计':<20}{total_before:>8}{total_after:>8}{total_before - total_after:>8}")
    return "\n".join(lines)