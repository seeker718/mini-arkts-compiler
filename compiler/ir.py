"""三地址码中间表示（实验三）。

设计要点（对应大纲「IR设计与生成」）：

1. **三地址码形式**：借鉴 LLVM IR 的思想——每条指令至多一个目标值、最多两个源操作数，
   操作数可以是字面量常量、命名变量（``%x``）或临时变量（``%t1``）；
2. **基本块组织控制流**：以 :class:`IRBasicBlock` 为单位组织指令，配合 ``br`` / ``jmp``
   与标签表达顺序、分支与循环；
3. **DeviceID 维度**：每条指令与每个函数都带 ``device`` 字段（0 表示本机，其余为模拟的远端设备），
   这是为「分布式软总线」思想预留的维度，供调度与跨设备代码生成使用；
4. **SSA 的简化模拟**：变量被重新赋值时产生新的版本名（``%x`` → ``%x.1`` → ``%x.2``），
   分支汇合处用 ``phi`` 指令合并不同路径上的版本。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------- 操作码
OP_ASSIGN = "assign"
OP_ADD = "add"
OP_SUB = "sub"
OP_MUL = "mul"
OP_DIV = "div"
OP_MOD = "mod"
OP_LT = "lt"
OP_GT = "gt"
OP_LE = "le"
OP_GE = "ge"
OP_EQ = "eq"
OP_NE = "ne"
OP_LAND = "land"
OP_LOR = "lor"
OP_NEG = "neg"
OP_NOT = "not"
OP_BNOT = "bnot"
OP_BAND = "band"
OP_BOR = "bor"
OP_BXOR = "bxor"
OP_SHL = "shl"
OP_SHR = "shr"
OP_CALL = "call"
OP_RET = "ret"
OP_BR = "br"
OP_JMP = "jmp"
OP_PHI = "phi"
OP_NEW = "new"
OP_FIELD_LOAD = "field.load"
OP_FIELD_STORE = "field.store"
OP_ARRAY_NEW = "array.new"
OP_ARRAY_LOAD = "array.load"
OP_ARRAY_STORE = "array.store"

# 二元运算操作码集合
BINARY_OPS = {
    OP_ADD, OP_SUB, OP_MUL, OP_DIV, OP_MOD,
    OP_LT, OP_GT, OP_LE, OP_GE, OP_EQ, OP_NE,
    OP_LAND, OP_LOR, OP_BAND, OP_BOR, OP_BXOR, OP_SHL, OP_SHR,
}
# 会调用外部 / 产生副作用的操作码（分布式 Pass 判定纯度时使用）
SIDE_EFFECT_OPS = {OP_CALL, OP_FIELD_STORE, OP_ARRAY_STORE, OP_NEW}


@dataclass
class IRInstruction:
    """一条三地址码指令。"""

    op: str
    dst: str | None = None
    args: list = field(default_factory=list)
    device: int = 0
    lineno: int = 0

    # ---------------------------------------------------------- 打印
    def to_text(self) -> str:
        body = self._body_text()
        if self.device:
            return f"{body}    ; dev={self.device}"
        return body

    def _body_text(self) -> str:
        if self.op == OP_RET:
            return f"ret {self.args[0]}" if self.args else "ret"
        if self.op == OP_BR:
            return f"br {self.args[0]}, {self.args[1]}, {self.args[2]}"
        if self.op == OP_JMP:
            return f"jmp {self.args[0]}"
        if self.op == OP_PHI:
            items = ", ".join(f"[{v}, {label}]" for v, label in self.args)
            return f"{self.dst} = phi {items}"
        if self.op == OP_CALL:
            func = self.args[0]
            rest = ", ".join(self.args[1:])
            return f"{self.dst} = call {func}({rest})"
        if self.op in (OP_FIELD_LOAD, OP_ARRAY_LOAD):
            return f"{self.dst} = {self.op} " + ", ".join(self.args)
        if self.op in (OP_FIELD_STORE, OP_ARRAY_STORE):
            return f"{self.op} " + ", ".join(self.args)
        if self.op == OP_NEW:
            return f"{self.dst} = new {self.args[0]}"
        if self.op == OP_ARRAY_NEW:
            return f"{self.dst} = array.new {self.args[0]}"
        if self.op in BINARY_OPS:
            return f"{self.dst} = {self.op} {self.args[0]}, {self.args[1]}"
        if self.dst:
            return f"{self.dst} = {self.op} " + ", ".join(self.args)
        return f"{self.op} " + ", ".join(self.args)


@dataclass
class IRBasicBlock:
    """基本块：一个标签 + 一串顺序执行的指令。"""

    label: str
    instructions: list[IRInstruction] = field(default_factory=list)


@dataclass
class IRFunction:
    """一个 IR 函数（也用于表示类的方法）。"""

    name: str
    params: list[str] = field(default_factory=list)
    return_type: str = "void"
    blocks: list[IRBasicBlock] = field(default_factory=list)
    local_types: dict = field(default_factory=dict)  # 局部变量 IR 名 -> 源语言类型名
    param_types: list = field(default_factory=list)  # 参数类型名
    device_id: int = 0
    cross_device: bool = False
    is_method: bool = False
    owner: str | None = None

    def block(self, label: str) -> IRBasicBlock:
        for b in self.blocks:
            if b.label == label:
                return b
        return None

    def all_instructions(self):
        for block in self.blocks:
            yield from block.instructions

    def instruction_count(self) -> int:
        return sum(len(b.instructions) for b in self.blocks)

    def to_text(self) -> str:
        tag = ""
        if self.cross_device:
            tag = f"  ; cross-device (device={self.device_id})"
        head = f"func {self.name}({', '.join(self.params)}) -> {self.return_type} {{{tag}"
        lines = [head]
        for block in self.blocks:
            lines.append(f"{block.label}:")
            for ins in block.instructions:
                lines.append("  " + ins.to_text())
        lines.append("}")
        return "\n".join(lines)


@dataclass
class IRModule:
    """一个编译单元（对应一份 .ets 源文件）。"""

    name: str = "mini_arkts_module"
    functions: list[IRFunction] = field(default_factory=list)
    globals: list = field(default_factory=list)  # (name, type_name)
    device_list: list = field(default_factory=list)  # 模拟设备拓扑 (id, name)

    def function(self, name: str) -> IRFunction | None:
        for f in self.functions:
            if f.name == name:
                return f
        return None

    def to_text(self) -> str:
        lines = [f"module {self.name}", ""]
        if self.globals:
            for gname, gtype in self.globals:
                lines.append(f"  global {gname}: {gtype}")
            lines.append("")
        for func in self.functions:
            lines.append(func.to_text())
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def stats(self) -> dict:
        return {
            "functions": len(self.functions),
            "blocks": sum(len(f.blocks) for f in self.functions),
            "instructions": sum(f.instruction_count() for f in self.functions),
            "cross_device": sum(1 for f in self.functions if f.cross_device),
        }