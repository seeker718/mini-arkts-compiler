"""实验三 · Mock-C 代码生成单元测试。"""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler import cgen, ir, irgen  # noqa: E402
from compiler.lexer import tokenize  # noqa: E402
from compiler.parser import parse  # noqa: E402
from compiler.sema import analyze  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


def gen_c(src: str) -> str:
    tokens, _ = tokenize(src)
    program, _ = parse(tokens)
    _, analyzer = analyze(program)
    module = irgen.generate(program, analyzer)
    return cgen.generate_c(module)


class TestCGen(unittest.TestCase):
    def test_contains_runtime_preamble(self):
        c = gen_c("function f(): number { return 1; }")
        self.assertIn("#include <stdio.h>", c)
        self.assertIn("ark_console_log_number", c)

    def test_function_name_has_ark_prefix(self):
        c = gen_c("function add(a: number, b: number): number { return a + b; }")
        self.assertIn("ark_add(", c)

    def test_main_is_generated(self):
        c = gen_c("function demo(): number { return 0; }")
        self.assertIn("int main(void)", c)
        self.assertIn("ark_demo()", c)

    def test_phi_is_eliminated_by_goto(self):
        src = ("function f(c: boolean): number {"
               " let x: number = 1;"
               " if (c) { x = 2; } else { x = 3; }"
               " return x; }")
        c = gen_c(src)
        self.assertNotIn("phi", c.lower())
        self.assertIn("goto", c)

    def test_while_becomes_labels_and_goto(self):
        src = ("function f(n: number): number {"
               " let s: number = 0; let i: number = 0;"
               " while (i < n) { s = s + i; i++; }"
               " return s; }")
        c = gen_c(src)
        self.assertIn("goto", c)
        self.assertIn("L_while_cond", c)
        self.assertIn("L_while_end", c)

    def test_string_concat_uses_helper(self):
        c = gen_c('function f(): string { return "a" + "b"; }')
        self.assertIn("ark_str_concat", c)

    def test_class_generates_struct(self):
        src = "class P { x: number = 0; y: number = 0; get(): number { return this.x; } }"
        c = gen_c(src)
        self.assertIn("typedef struct P", c)
        self.assertIn("->x", c)
        self.assertIn("ark_P_get(", c)

    def test_unresolved_call_is_guarded(self):
        module = ir.IRModule(name="m")
        func = ir.IRFunction(name="f", return_type="number")
        func.blocks.append(ir.IRBasicBlock("entry", [
            ir.IRInstruction(op=ir.OP_CALL, dst="%t1", args=["nope", "1"]),
            ir.IRInstruction(op=ir.OP_RET, args=["%t1"]),
        ]))
        module.functions.append(func)
        c = cgen.generate_c(module)
        self.assertIn("未解析的外部调用", c)

    def test_real_sample_generates_expected_functions(self):
        source = (ROOT / "samples" / "ir_demo.ets").read_text(encoding="utf-8")
        tokens, _ = tokenize(source)
        program, _ = parse(tokens)
        _, analyzer = analyze(program)
        module = irgen.generate(program, analyzer)
        c = cgen.generate_c(module)
        for name in ("ark_square", "ark_sumTo", "ark_classify", "ark_demo"):
            self.assertIn(name, c)


if __name__ == "__main__":
    unittest.main()