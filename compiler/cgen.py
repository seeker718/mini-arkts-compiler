"""IR -> Mock-C 代码生成（实验三）。

生成标准 C99 代码，交给 GCC / Clang 即可编译运行。为体现「调用约定模拟鸿蒙 API」，
所有用户函数统一加 ``ark_`` 前缀，并在文件头提供一组运行时桩（console 输出、
字符串拼接等），相当于一个极简的鸿蒙 API 模拟层。

φ 指令在 C 中没有对应物，采用「在前驱块跳转前插入赋值」的方式消除，
这与真实的 SSA 消除（out-of-SSA）思路一致。
"""

from __future__ import annotations

from . import ir

_RUNTIME = r"""/* ================= Mini-ArkTS 运行时桩（模拟鸿蒙 API 调用约定） ================= */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

typedef double      ark_number;
typedef const char* ark_string;
typedef int         ark_bool;

static ark_string ark_str_concat(ark_string a, ark_string b) {
    size_t la = strlen(a), lb = strlen(b);
    char *r = (char *)malloc(la + lb + 1);
    memcpy(r, a, la);
    memcpy(r + la, b, lb + 1);
    return r;
}

static ark_string ark_str_of_number(ark_number n) {
    static char buf[64];
    snprintf(buf, sizeof(buf), "%g", n);
    return buf;
}

static void ark_console_log_number(ark_number n) { printf("%g\n", n); }
static void ark_console_log_string(ark_string s) { printf("%s\n", s); }

#define ARK_TRUE  1
#define ARK_FALSE 0
"""

_RUNTIME_SYMBOLS = {
    "ark_str_concat",
    "ark_str_of_number",
    "ark_console_log_number",
    "ark_console_log_string",
}

_C_TYPE = {
    "number": "ark_number",
    "string": "ark_string",
    "boolean": "ark_bool",
    "void": "void",
    "array": "ark_number*",
}

_BINOP_C = {
    ir.OP_ADD: "+", ir.OP_SUB: "-", ir.OP_MUL: "*", ir.OP_DIV: "/",
    ir.OP_LT: "<", ir.OP_GT: ">", ir.OP_LE: "<=", ir.OP_GE: ">=",
    ir.OP_EQ: "==", ir.OP_NE: "!=",
    ir.OP_LAND: "&&", ir.OP_LOR: "||",
    ir.OP_BAND: "&", ir.OP_BOR: "|", ir.OP_BXOR: "^",
}


class CGenerator:
    def __init__(self, module: ir.IRModule, entry: str = "demo") -> None:
        self.module = module
        self.entry = entry
        self.lines: list[str] = []
        self.structs: dict[str, list[str]] = {}
        self.known: set[str] = set(_RUNTIME_SYMBOLS)
        self.func: ir.IRFunction | None = None
        self.var_types: dict[str, str] = {}

    # ------------------------------------------------------------ 对外接口
    def generate(self) -> str:
        self._collect_structs()
        self.known |= {self._c_func_name(f.name) for f in self.module.functions}

        out: list[str] = ["/* ==== 由 Mini-ArkTS 编译器自动生成（实验三 Mock-C） ==== */"]
        out.append(_RUNTIME)
        out.append(self._emit_structs())
        for func in self.module.functions:
            out.append(self._emit_function(func))
        out.append(self._emit_main())
        return "\n".join(line for line in out if line is not None)

    # ------------------------------------------------------------ 准备
    def _collect_structs(self) -> None:
        for name, _type in self.module.globals:
            if name.startswith("@") and "." in name:
                cls, field = name[1:].split(".", 1)
                self.structs.setdefault(cls, []).append(self._field_name(field))

    def _emit_structs(self) -> str:
        if not self.structs:
            return ""
        lines = ["/* ================= 类 / 组件（简化为 C 结构体） ================= */"]
        for cls, fields in self.structs.items():
            body = " ".join(f"ark_number {f};" for f in fields)
            lines.append(f"typedef struct {cls} {{ {body} }} {cls};")
        return "\n".join(lines)

    # ------------------------------------------------------------ 函数
    def _emit_function(self, func: ir.IRFunction) -> str:
        self.func = func
        self.var_types = dict(func.local_types)

        ret = _C_TYPE.get(func.return_type, "ark_number")
        params = []
        if func.is_method:
            params.append(f"{func.owner}* self")
            self.var_types["%this"] = func.owner
        for pname, ptype in zip(func.params, func.param_types):
            params.append(f"{_C_TYPE.get(ptype, 'ark_number')} {self._c_name(pname)}")

        lines = [""]
        if func.cross_device:
            lines.append(f"/* 可跨设备执行（device={func.device_id}），由 RPC Skeleton 调用 */")
        lines.append(f"static {ret} {self._c_func_name(func.name)}({', '.join(params)}) {{")

        for decl in self._local_declarations(func):
            lines.append("    " + decl)

        for block in func.blocks:
            lines.append(f"{self._c_label(block.label)}:")
            for ins in block.instructions:
                for stmt in self._emit_instruction(ins, block.label):
                    lines.append("    " + stmt)
        lines.append("}")
        self.func = None
        return "\n".join(lines)

    def _local_declarations(self, func: ir.IRFunction) -> list[str]:
        declared = set(p for p in func.params)
        declared.add("%this")
        order: list[str] = []
        for block in func.blocks:
            for ins in block.instructions:
                if ins.dst and ins.dst not in declared and ins.dst not in order:
                    order.append(ins.dst)
        result = []
        for ir_name in order:
            ctype = self._c_decl_type(ir_name)
            result.append(f"{ctype} {self._c_name(ir_name)};")
        return result

    def _c_decl_type(self, ir_name: str) -> str:
        t = self.var_types.get(ir_name, "number")
        if t in _C_TYPE:
            return _C_TYPE[t]
        return f"{t}*"  # 类对象用指针

    # ------------------------------------------------------------ 指令翻译
    def _emit_instruction(self, ins: ir.IRInstruction, block_label: str) -> list[str]:
        op = ins.op
        if op == ir.OP_PHI:
            return []  # φ 由前驱块负责赋值

        if op == ir.OP_ASSIGN:
            return [f"{self._operand(ins.dst)} = {self._operand(ins.args[0])};"]

        if op in _BINOP_C:
            left, right = ins.args[0], ins.args[1]
            a, b = self._operand(left), self._operand(right)
            if self._is_string(left) and self._is_string(right):
                return [f"{self._operand(ins.dst)} = ark_str_concat({a}, {b});"]
            return [f"{self._operand(ins.dst)} = {a} {_BINOP_C[op]} {b};"]

        if op == ir.OP_MOD:
            return [f"{self._operand(ins.dst)} = fmod({self._operand(ins.args[0])}, "
                    f"{self._operand(ins.args[1])});"]
        if op == ir.OP_SHL:
            return [f"{self._operand(ins.dst)} = (ark_number)((long){self._operand(ins.args[0])} "
                    f"<< (long){self._operand(ins.args[1])});"]
        if op == ir.OP_SHR:
            return [f"{self._operand(ins.dst)} = (ark_number)((long){self._operand(ins.args[0])} "
                    f">> (long){self._operand(ins.args[1])});"]
        if op == ir.OP_NEG:
            return [f"{self._operand(ins.dst)} = -{self._operand(ins.args[0])};"]
        if op == ir.OP_NOT:
            return [f"{self._operand(ins.dst)} = !{self._operand(ins.args[0])};"]
        if op == ir.OP_BNOT:
            return [f"{self._operand(ins.dst)} = (ark_number)(~(long){self._operand(ins.args[0])});"]

        if op == ir.OP_CALL:
            name = ins.args[0]
            cname = self._c_func_name(name)
            args = ", ".join(self._operand(a) for a in ins.args[1:])
            if cname not in self.known:
                return [f"{self._operand(ins.dst)} = 0; /* 未解析的外部调用: {name} */"]
            return [f"{self._operand(ins.dst)} = {cname}({args});"]

        if op == ir.OP_RET:
            if ins.args:
                return [f"return {self._operand(ins.args[0])};"]
            return ["return;"]

        if op == ir.OP_JMP:
            phi = self._phi_assignments(ins.args[0], block_label)
            return phi + [f"goto {self._c_label(ins.args[0])};"]

        if op == ir.OP_BR:
            cond, true_label, false_label = ins.args
            phi_true = self._phi_assignments(true_label, block_label)
            phi_false = self._phi_assignments(false_label, block_label)
            true_stmt = " ".join(phi_true + [f"goto {self._c_label(true_label)};"])
            false_stmt = " ".join(phi_false + [f"goto {self._c_label(false_label)};"])
            return [f"if ({self._operand(cond)}) {{ {true_stmt} }} else {{ {false_stmt} }}"]

        if op == ir.OP_NEW:
            cls = ins.args[0]
            return [f"{self._operand(ins.dst)} = ({cls}*)calloc(1, sizeof({cls}));"]

        if op == ir.OP_FIELD_LOAD:
            obj, field = ins.args
            return [f"{self._operand(ins.dst)} = {self._operand(obj)}->"
                    f"{self._field_name(field)};"]

        if op == ir.OP_FIELD_STORE:
            obj, field, value = ins.args
            return [f"{self._operand(obj)}->{self._field_name(field)} = "
                    f"{self._operand(value)};"]

        if op == ir.OP_ARRAY_NEW:
            return [f"{self._operand(ins.dst)} = (ark_number*)calloc("
                    f"{ins.args[0]}, sizeof(ark_number));"]

        if op == ir.OP_ARRAY_STORE:
            arr, index, value = ins.args
            return [f"{self._operand(arr)}[(int)({self._operand(index)})] = "
                    f"{self._operand(value)};"]

        if op == ir.OP_ARRAY_LOAD:
            arr, index = ins.args
            return [f"{self._operand(ins.dst)} = "
                    f"{self._operand(arr)}[(int)({self._operand(index)})];"]

        return [f"/* 未支持的操作: {op} */"]

    def _phi_assignments(self, target_label: str, pred_label: str) -> list[str]:
        block = self.func.block(target_label) if self.func else None
        if block is None:
            return []
        stmts = []
        for ins in block.instructions:
            if ins.op != ir.OP_PHI:
                continue
            for value, label in ins.args:
                if label == pred_label:
                    stmts.append(f"{self._operand(ins.dst)} = {self._operand(value)};")
                    break
        return stmts

    # ------------------------------------------------------------ main
    def _emit_main(self) -> str:
        candidates = [self.entry, "main", "demo"]
        target = None
        for name in candidates:
            if self.module.function(name) is not None:
                target = name
                break
        lines = ["", "int main(void) {"]
        if target is not None:
            lines.append(f"    ark_console_log_number({self._c_func_name(target)}());")
        else:
            lines.append('    ark_console_log_string("(no entry function)");')
        lines.append("    return 0;")
        lines.append("}")
        return "\n".join(lines)

    # ------------------------------------------------------------ 名字与操作数
    def _is_string(self, operand: str) -> bool:
        if operand is None:
            return False
        if operand.startswith('"'):
            return True
        t = self.var_types.get(operand)
        return t == "string"

    def _operand(self, value) -> str:
        if value is None:
            return "0"
        if value == "true":
            return "ARK_TRUE"
        if value == "false":
            return "ARK_FALSE"
        if value.startswith("%"):
            return self._c_name(value)
        return str(value)

    def _c_name(self, ir_name: str) -> str:
        name = ir_name
        if name.startswith("%") or name.startswith("@"):
            name = name[1:]
        name = name.replace(".", "_")
        if ir_name == "%this":
            return "self"
        return f"v_{name}" if name and not name[0].isdigit() else f"v_{name}"

    @staticmethod
    def _field_name(name: str) -> str:
        return name.replace(".", "_").replace("@", "").replace("%", "")

    def _c_func_name(self, name: str) -> str:
        return "ark_" + name.replace(".", "_").replace("@", "")

    @staticmethod
    def _c_label(label: str) -> str:
        return "L_" + label.replace(".", "_")


def generate_c(module: ir.IRModule, entry: str = "demo") -> str:
    """便捷函数：IRModule -> Mock-C 源码字符串。"""
    return CGenerator(module, entry).generate()