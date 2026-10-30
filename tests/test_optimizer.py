"""实验四 · IR 优化 Pass 单元测试。"""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler import cgen, ir, irgen  # noqa: E402
from compiler.lexer import tokenize  # noqa: E402
from compiler.optimizer import diff_text, optimize  # noqa: E402
from compiler.parser import parse  # noqa: E402
from compiler.sema import analyze  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
SAMPLE = (ROOT / "samples" / "optimize_demo.ets").read_text(encoding="utf-8")


def build(src: str) -> ir.IRModule:
    tokens, lex_errors = tokenize(src)
    program, parse_errors = parse(tokens)
    sema_errors, analyzer = analyze(program)
    assert not (lex_errors or parse_errors or sema_errors), (lex_errors, parse_errors, sema_errors)
    return irgen.generate(program, analyzer)


class TestOptimizer(unittest.TestCase):
    def test_constant_folding(self):
        module = build("function f(): number { let a: number = 2 + 3 * 4; return a; }")
        optimize(module)
        text = module.function("f").to_text()
        self.assertIn("14", text)                 # 2 + 3 * 4 被折叠
        self.assertNotIn("mul", text)             # 乘法指令已消失

    def test_constant_propagation_into_next_expression(self):
        src = ("function f(): number {"
               " let a: number = 2 + 3;"
               " let b: number = a * 2;"
               " return b; }")
        module = build(src)
        optimize(module)
        text = module.function("f").to_text()
        self.assertIn("10", text)                 # 一路折叠传播到 ret 10
        self.assertNotIn("mul", text)
        self.assertNotIn("add", text)

    def test_string_concat_folding(self):
        module = build('function f(): string { let s: string = "a" + "b"; return s; }')
        optimize(module)
        self.assertIn('"ab"', module.function("f").to_text())

    def test_dead_branch_is_removed(self):
        src = ("function f(): number {"
               " let x: number = 1;"
               " if (false) { x = 99; }"
               " return x; }")
        module = build(src)
        before = module.function("f").instruction_count()
        optimize(module)
        func = module.function("f")
        self.assertLess(func.instruction_count(), before)
        self.assertNotIn("if.then", func.to_text())

    def test_true_branch_is_kept_and_else_dropped(self):
        src = ("function f(): number {"
               " let x: number = 1;"
               " if (true) { x = 2; } else { x = 3; }"
               " return x; }")
        module = build(src)
        optimize(module)
        text = module.function("f").to_text()
        self.assertIn("ret 2", text)
        self.assertNotIn("assign 3", text)

    def test_unused_assignment_is_removed(self):
        src = ("function f(): number {"
               " let x: number = 1;"
               " let unused: number = x * 100;"
               " return x; }")
        module = build(src)
        optimize(module)
        self.assertNotIn("unused", module.function("f").to_text())

    def test_side_effect_call_is_not_removed(self):
        src = ("function g(): number { return 1; }\n"
               "function f(): number { let x: number = g(); return 2; }")
        module = build(src)
        optimize(module)
        # 函数调用可能带副作用，不能被当作死代码删除
        self.assertIn("call g(", module.function("f").to_text())

    def test_stats_are_reported(self):
        module = build(SAMPLE)
        stats = optimize(module)
        self.assertGreater(stats["constant_folded"], 0)
        self.assertLessEqual(stats["after"], stats["before"])
        self.assertGreater(
            stats["constant_folded"] + stats["block_removed"] + stats["instruction_removed"], 0
        )

    def test_optimized_module_still_generates_c(self):
        module = build(SAMPLE)
        optimize(module)
        c = cgen.generate_c(module)
        self.assertIn("ark_demo", c)

    def test_diff_text(self):
        before = build(SAMPLE)
        after = build(SAMPLE)
        optimize(after)
        text = diff_text(before, after)
        self.assertIn("优化前后对比", text)
        self.assertIn("合计", text)


if __name__ == "__main__":
    unittest.main()