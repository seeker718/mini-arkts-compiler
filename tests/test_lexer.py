"""实验一 · 词法分析器单元测试。"""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler.lexer import tokenize  # noqa: E402
from compiler.tokens import TokenType as T  # noqa: E402


class TestLexer(unittest.TestCase):
    def types(self, src: str):
        tokens, errors = tokenize(src)
        return [t.type for t in tokens], errors

    def test_keywords(self):
        types, errors = self.types("let const if else while for class struct")
        self.assertEqual(
            types[:8],
            [T.LET, T.CONST, T.IF, T.ELSE, T.WHILE, T.FOR, T.CLASS, T.STRUCT],
        )
        self.assertEqual(types[-1], T.EOF)
        self.assertEqual(errors, [])

    def test_identifier_and_decorator(self):
        types, errors = self.types("@Entry Component")
        self.assertEqual(types[:3], [T.AT, T.IDENTIFIER, T.IDENTIFIER])
        self.assertEqual(errors, [])

    def test_number_literals(self):
        tokens, _ = tokenize("0 42 3.14 1e3 0xFF 0b1010 1_000")
        values = [t.value for t in tokens[:-1]]
        self.assertEqual(values, ["0", "42", "3.14", "1e3", "0xFF", "0b1010", "1_000"])

    def test_string_literals(self):
        tokens, errors = tokenize("'a\\n' \"b\" `t${x}`")
        self.assertEqual([t.type for t in tokens[:-1]], [T.STRING, T.STRING, T.TEMPLATE_STRING])
        self.assertEqual(errors, [])

    def test_comments_are_skipped(self):
        types, errors = self.types("let x = 1; // line\n/* block */ const y = 2;")
        self.assertNotIn(T.EOF, types[:-1])
        self.assertEqual(errors, [])
        self.assertEqual(types.count(T.LET), 1)
        self.assertEqual(types.count(T.CONST), 1)

    def test_multichar_operators(self):
        types, _ = self.types("=== !== >>> => ?. << >> ++ --")
        self.assertEqual(
            types[:10],
            [T.STRICT_EQ, T.STRICT_NEQ, T.USHR, T.ARROW, T.OPTIONAL_CHAIN,
             T.SHL, T.SHR, T.INCREMENT, T.DECREMENT, T.EOF],
        )

    def test_line_and_column_tracking(self):
        tokens, _ = tokenize("let x;\n  let y;")
        y = [t for t in tokens if t.value == "y"][0]
        self.assertEqual((y.line, y.column), (2, 7))

    def test_unterminated_string_reports_error(self):
        _, errors = tokenize("let s = 'abc")
        self.assertTrue(any("未闭合的字符串" in e.message for e in errors))

    def test_unterminated_block_comment_reports_error(self):
        _, errors = tokenize("/* never closed")
        self.assertTrue(any("未闭合的块注释" in e.message for e in errors))

    def test_illegal_char_reports_error_and_continues(self):
        tokens, errors = tokenize("let a = #; let b = 2;")
        self.assertTrue(any("非法字符" in e.message for e in errors))
        # 出错后仍能继续产出后续 Token
        self.assertEqual([t.value for t in tokens].count("let"), 2)


if __name__ == "__main__":
    unittest.main()