"""实验二 · 语义分析与类型检查单元测试。"""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler.lexer import tokenize  # noqa: E402
from compiler.parser import parse  # noqa: E402
from compiler.sema import analyze  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


def run(src: str):
    tokens, lex_errors = tokenize(src)
    program, parse_errors = parse(tokens)
    sema_errors, analyzer = analyze(program)
    return program, analyzer, sema_errors, lex_errors + parse_errors


class TestSemanticAnalysis(unittest.TestCase):
    def messages(self, src: str) -> list[str]:
        _, _, errors, syntax = run(src)
        self.assertEqual(syntax, [], f"源码不应有词法/语法错误: {syntax}")
        return [e.message for e in errors]

    def assertReports(self, src: str, keyword: str) -> None:
        messages = self.messages(src)
        self.assertTrue(
            any(keyword in m for m in messages),
            f"期望报出包含 {keyword!r} 的错误，实际为 {messages}",
        )

    # ---- 合法代码 ----
    def test_ok_sample_has_no_semantic_error(self):
        source = (ROOT / "samples" / "sema_ok.ets").read_text(encoding="utf-8")
        tokens, lex_errors = tokenize(source)
        program, parse_errors = parse(tokens)
        self.assertEqual(lex_errors + parse_errors, [])
        sema_errors, _ = analyze(program)
        self.assertEqual([e.message for e in sema_errors], [])

    def test_type_inference(self):
        _, analyzer, errors, _ = run("let n = 1;")
        self.assertEqual(errors, [])
        symbol = analyzer.symbols.resolve("n")
        self.assertEqual(str(symbol.type), "number")
        self.assertTrue(symbol.inferred)

    # ---- 类型不匹配 ----
    def test_string_to_number_reports(self):
        self.assertReports("let x: number = 'text';", "类型不匹配")

    def test_number_to_string_reports(self):
        self.assertReports("let s: string = 1;", "类型不匹配")

    def test_number_plus_string_reports(self):
        self.assertReports("let z: number = 1; z = z + 'a';", "无法作用于")

    def test_inferred_type_checked_on_reassignment(self):
        self.assertReports("let n = 1; n = 'a';", "类型不匹配")

    # ---- 作用域与声明 ----
    def test_undeclared_variable_reports(self):
        self.assertReports("let y: number = notDeclared;", "未声明的标识符")

    def test_duplicate_declaration_reports(self):
        self.assertReports("let a: number = 1; let a: number = 2;", "重复定义")

    def test_assign_to_const_reports(self):
        self.assertReports("const c: number = 1; c = 2;", "不能给常量")

    # ---- 控制流 ----
    def test_if_condition_must_be_boolean(self):
        self.assertReports("let z: number = 1; if (z) { }", "条件必须是 boolean")

    def test_while_condition_must_be_boolean(self):
        self.assertReports("let z: number = 1; while (z) { }", "条件必须是 boolean")

    def test_break_outside_loop_reports(self):
        self.assertReports("break;", "break 只能出现在循环")

    # ---- 函数 ----
    def test_return_type_mismatch_reports(self):
        self.assertReports("function f(): number { return 'x'; }", "返回类型不匹配")

    def test_argument_count_reports(self):
        self.assertReports("function g(a: number): void { } g();", "参数个数不足")

    def test_argument_type_reports(self):
        self.assertReports("function g(a: number): void { } g('x');", "参数类型不匹配")

    def test_call_undeclared_function_reports(self):
        self.assertReports("noSuchFunction();", "未声明的函数")

    # ---- 类与成员 ----
    def test_private_member_access_reports(self):
        src = (
            "class Base { private secret: number = 1; }\n"
            "let b: Base = new Base();\n"
            "let s: number = b.secret;"
        )
        self.assertReports(src, "private")

    def test_missing_member_reports(self):
        src = "class Base { value: number = 1; }\nlet b: Base = new Base();\nlet v: number = b.missing;"
        self.assertReports(src, "不存在成员")

    def test_interface_implementation_reports(self):
        src = "interface Shape { area(): number; }\nclass Circle implements Shape { radius: number = 1; }"
        self.assertReports(src, "未实现成员")

    def test_array_element_type_mismatch_reports(self):
        self.assertReports("let a: number[] = [1, 'x'];", "数组元素类型不一致")

    # ---- 装饰器语义 ----
    def test_state_outside_entry_reports(self):
        src = "@Component\nstruct S { @State n: number = 0; }"
        self.assertReports(src, "@Entry")

    def test_state_in_plain_class_reports(self):
        src = "class C { @State n: number = 0; }"
        self.assertReports(src, "struct 组件")

    def test_state_inside_entry_is_ok(self):
        src = "@Entry\n@Component\nstruct S { @State n: number = 0; }"
        self.assertEqual(self.messages(src), [])

    # ---- 错误定位 ----
    def test_error_has_position(self):
        _, _, errors, _ = run("let x: number = 'text';")
        self.assertTrue(errors)
        self.assertTrue(all(e.line >= 1 and e.column >= 1 for e in errors))


if __name__ == "__main__":
    unittest.main()