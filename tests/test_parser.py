"""实验一 · 语法分析器（递归下降）单元测试。"""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler.ast_json import to_json, to_sexpr  # noqa: E402
from compiler.lexer import tokenize  # noqa: E402
from compiler.parser import parse  # noqa: E402


def parse_src(src: str):
    tokens, lex_errors = tokenize(src)
    ast, parse_errors = parse(tokens)
    return ast, lex_errors + parse_errors


class TestParser(unittest.TestCase):
    def test_variable_declaration(self):
        ast, errors = parse_src("let x: number = 1;")
        self.assertEqual(errors, [])
        self.assertIn("VariableDeclaration", to_sexpr(ast))
        self.assertIn("TypeAnnotation", to_sexpr(ast))

    def test_if_else(self):
        ast, errors = parse_src("if (a > 1) { b = 1; } else { b = 2; }")
        self.assertEqual(errors, [])
        s = to_sexpr(ast)
        self.assertIn("IfStatement", s)
        self.assertIn("alternate", s)  # 存在 else 分支

    def test_if_without_else(self):
        ast, errors = parse_src("if (a) { b = 1; }")
        self.assertEqual(errors, [])
        self.assertNotIn("alternate=", to_sexpr(ast))

    def test_while_loop(self):
        ast, errors = parse_src("while (i < 10) { i++; }")
        self.assertEqual(errors, [])
        self.assertIn("WhileStatement", to_sexpr(ast))

    def test_for_loop(self):
        ast, errors = parse_src("for (let i = 0; i < 3; i++) { x = x + 1; }")
        self.assertEqual(errors, [])
        self.assertIn("ForStatement", to_sexpr(ast))

    def test_function_declaration(self):
        ast, errors = parse_src("function add(a: number, b: number): number { return a + b; }")
        self.assertEqual(errors, [])
        s = to_sexpr(ast)
        self.assertIn("FunctionDeclaration", s)
        self.assertIn("ReturnStatement", s)

    def test_operator_precedence(self):
        ast, errors = parse_src("let r = 1 + 2 * 3;")
        self.assertEqual(errors, [])
        s = to_sexpr(ast)
        # 乘法应比加法更深一层：(BinaryExpression op=+ (BinaryExpression op=* ...))
        self.assertIn("op=+", s.replace("operator=", "op="))
        self.assertLess(s.index("operator=+"), s.index("operator=*"))

    def test_struct_with_decorators(self):
        src = "@Entry @Component struct Page { @State n: number = 0; build() { Text('hi') } }"
        ast, errors = parse_src(src)
        self.assertEqual(errors, [])
        s = to_sexpr(ast)
        self.assertIn("ClassDeclaration", s)
        self.assertIn("kind=struct", s)
        self.assertIn("Decorator", s)
        self.assertIn("MethodDeclaration", s)

    def test_ui_container(self):
        src = "struct P { build() { Column() { Text('hi'); Row() { Text('r') } } } }"
        ast, errors = parse_src(src)
        self.assertEqual(errors, [])
        self.assertIn("UiContainer", to_sexpr(ast))

    def test_ui_components_allow_missing_semicolon(self):
        src = "struct P { build() { Column() { Text('a')\nButton('b') } } }"
        ast, errors = parse_src(src)
        self.assertEqual(errors, [])
        s = to_sexpr(ast)
        self.assertIn("UiContainer", s)
        self.assertEqual(s.count("ExpressionStatement"), 2)

    def test_arrow_function_block_body(self):
        ast, errors = parse_src("let f = (a: number) => { return a + 1; };")
        self.assertEqual(errors, [])
        self.assertIn("ArrowFunctionExpression", to_sexpr(ast))

    def test_arrow_function_expression_body(self):
        ast, errors = parse_src("let g = x => x * 2;")
        self.assertEqual(errors, [])
        self.assertIn("ArrowFunctionExpression", to_sexpr(ast))

    def test_member_chain(self):
        ast, errors = parse_src("let v = this.count + arr[0];")
        self.assertEqual(errors, [])
        s = to_sexpr(ast)
        self.assertIn("MemberExpression", s)
        self.assertIn("computed=True", s)

    def test_conditional_expression(self):
        ast, errors = parse_src("let v = a > b ? a : b;")
        self.assertEqual(errors, [])
        self.assertIn("ConditionalExpression", to_sexpr(ast))

    def test_object_literal(self):
        ast, errors = parse_src("let o = { name: 'a', count: 1 };")
        self.assertEqual(errors, [])
        self.assertIn("ObjectLiteral", to_sexpr(ast))

    # ---- 错误处理 ----
    def test_missing_semicolon_reports_and_recovers(self):
        ast, errors = parse_src("let x = 1\nlet y = 2;")
        self.assertTrue(any("分号" in e.message for e in errors))
        # 恢复后第二条语句仍应被解析
        self.assertIn("VariableDeclaration", to_sexpr(ast))

    def test_unmatched_brace_reports(self):
        _, errors = parse_src("if (a) { b = 1;")
        self.assertTrue(any("'}'" in e.message for e in errors))

    def test_missing_expression_reports(self):
        _, errors = parse_src("let x = ;")
        self.assertTrue(errors)

    def test_error_position_is_recorded(self):
        _, errors = parse_src("let x = 1\nlet y = 2;")
        self.assertTrue(all(e.line >= 1 and e.column >= 1 for e in errors))

    def test_ast_json_is_serializable(self):
        ast, errors = parse_src("let x: number = 1;")
        self.assertEqual(errors, [])
        text = to_json(ast)
        self.assertIn('"type": "Program"', text)
        self.assertIn('"type": "VariableDeclaration"', text)


if __name__ == "__main__":
    unittest.main()