"""实验三 · AST -> IR 转换单元测试。"""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler import ir, irgen  # noqa: E402
from compiler.lexer import tokenize  # noqa: E402
from compiler.parser import parse  # noqa: E402
from compiler.sema import analyze  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


def gen(src: str) -> ir.IRModule:
    tokens, lex_errors = tokenize(src)
    program, parse_errors = parse(tokens)
    sema_errors, analyzer = analyze(program)
    assert not (lex_errors or parse_errors or sema_errors), (lex_errors, parse_errors, sema_errors)
    return irgen.generate(program, analyzer)


class TestIRGen(unittest.TestCase):
    def test_simple_function(self):
        module = gen("function add(a: number, b: number): number { return a + b; }")
        func = module.function("add")
        self.assertIsNotNone(func)
        self.assertEqual(len(func.params), 2)
        ops = [ins.op for ins in func.all_instructions()]
        self.assertIn(ir.OP_ADD, ops)
        self.assertIn(ir.OP_RET, ops)

    def test_variable_ssa_versions(self):
        module = gen("function f(): number { let x: number = 1; x = 2; return x; }")
        text = module.function("f").to_text()
        self.assertIn("assign", text)
        self.assertIn("%x", text)
        self.assertIn("%x.2", text)  # 第二次赋值产生新版本

    def test_if_generates_branch_and_phi(self):
        src = ("function f(c: boolean): number {"
               " let x: number = 1;"
               " if (c) { x = 2; } else { x = 3; }"
               " return x; }")
        text = gen(src).function("f").to_text()
        self.assertIn("br ", text)
        self.assertIn("phi", text)
        self.assertIn("if.then", text)
        self.assertIn("if.else", text)
        self.assertIn("if.end", text)

    def test_if_without_else_has_no_phi_for_untouched_var(self):
        src = ("function f(c: boolean): number {"
               " let x: number = 1;"
               " if (c) { x = 2; }"
               " return x; }")
        text = gen(src).function("f").to_text()
        self.assertIn("if.else", text)   # 仍然生成 else 空块
        self.assertIn("phi", text)

    def test_while_loop_blocks(self):
        src = ("function f(n: number): number {"
               " let s: number = 0; let i: number = 0;"
               " while (i < n) { s = s + i; i++; }"
               " return s; }")
        text = gen(src).function("f").to_text()
        for label in ("while.cond", "while.body", "while.end"):
            self.assertIn(label, text)
        self.assertIn("jmp", text)

    def test_for_loop_blocks(self):
        src = ("function f(n: number): number {"
               " let s: number = 0;"
               " for (let i: number = 0; i < n; i++) { s = s + i; }"
               " return s; }")
        text = gen(src).function("f").to_text()
        for label in ("for.cond", "for.body", "for.update", "for.end"):
            self.assertIn(label, text)

    def test_function_call(self):
        src = ("function g(x: number): number { return x; }\n"
               "function f(): number { return g(1); }")
        text = gen(src).function("f").to_text()
        self.assertIn("call g(", text)

    def test_class_method_ir(self):
        src = "class C { value: number = 0; get(): number { return this.value; } }"
        module = gen(src)
        method = module.function("C.get")
        self.assertIsNotNone(method)
        self.assertTrue(method.is_method)
        self.assertIn("%this", method.to_text())

    def test_global_variable_recorded(self):
        module = gen("let g: number = 1;")
        self.assertTrue(any(name == "@g" for name, _ in module.globals))

    def test_ui_build_is_skipped(self):
        src = ("@Entry @Component struct S { @State n: number = 0;"
               " build() { Column() { Text('hi') } } }")
        module = gen(src)
        self.assertIsNone(module.function("S.build"))

    def test_conditional_expression_uses_phi(self):
        src = "function f(c: boolean): number { let r: number = c ? 1 : 2; return r; }"
        text = gen(src).function("f").to_text()
        self.assertIn("cond.then", text)
        self.assertIn("phi", text)

    def test_real_sample_generates_ir(self):
        source = (ROOT / "samples" / "ir_demo.ets").read_text(encoding="utf-8")
        tokens, _ = tokenize(source)
        program, _ = parse(tokens)
        _, analyzer = analyze(program)
        module = irgen.generate(program, analyzer)
        names = [f.name for f in module.functions]
        for expected in ("square", "sumTo", "classify", "demo"):
            self.assertIn(expected, names)


if __name__ == "__main__":
    unittest.main()