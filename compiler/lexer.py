"""ArkTS 子集词法分析器（实验一）。

设计要点：
1. 单遍扫描（one-pass），用最长匹配识别运算符；
2. 错误不中断——遇到非法字符只记录诊断并跳过，尽可能产出完整 Token 流，
   方便实验四的模糊测试批量统计崩溃/异常；
3. 区分「关键字」与「标识符」：ArkTS 内在类型 number/string/boolean 被
   提升为关键字，这与实验二要实现的强类型检查相呼应。
"""

from __future__ import annotations

from .diagnostics import Diagnostic
from .tokens import Token, TokenType

# ---------------------------------------------------------------- 关键字表
KEYWORDS: dict[str, TokenType] = {
    "let": TokenType.LET,
    "const": TokenType.CONST,
    "var": TokenType.VAR,
    "function": TokenType.FUNCTION,
    "return": TokenType.RETURN,
    "if": TokenType.IF,
    "else": TokenType.ELSE,
    "while": TokenType.WHILE,
    "for": TokenType.FOR,
    "do": TokenType.DO,
    "break": TokenType.BREAK,
    "continue": TokenType.CONTINUE,
    "class": TokenType.CLASS,
    "struct": TokenType.STRUCT,
    "interface": TokenType.INTERFACE,
    "extends": TokenType.EXTENDS,
    "implements": TokenType.IMPLEMENTS,
    "enum": TokenType.ENUM,
    "new": TokenType.NEW,
    "this": TokenType.THIS,
    "super": TokenType.SUPER,
    "typeof": TokenType.TYPEOF,
    "instanceof": TokenType.INSTANCEOF,
    "in": TokenType.IN,
    "of": TokenType.OF,
    "true": TokenType.TRUE,
    "false": TokenType.FALSE,
    "null": TokenType.NULL,
    "undefined": TokenType.UNDEFINED,
    "void": TokenType.VOID,
    "public": TokenType.PUBLIC,
    "private": TokenType.PRIVATE,
    "protected": TokenType.PROTECTED,
    "static": TokenType.STATIC,
    "readonly": TokenType.READONLY,
    "async": TokenType.ASYNC,
    "await": TokenType.AWAIT,
    "import": TokenType.IMPORT,
    "export": TokenType.EXPORT,
    "from": TokenType.FROM,
    "as": TokenType.AS,
    "number": TokenType.NUMBER_TYPE,
    "string": TokenType.STRING_TYPE,
    "boolean": TokenType.BOOLEAN_TYPE,
    "any": TokenType.ANY_TYPE,
    "never": TokenType.NEVER_TYPE,
    "switch": TokenType.SWITCH,
    "case": TokenType.CASE,
    "default": TokenType.DEFAULT,
    "try": TokenType.TRY,
    "catch": TokenType.CATCH,
    "finally": TokenType.FINALLY,
    "throw": TokenType.THROW,
}

# ---------------------------------------------------------------- 运算符表
OPERATOR_MAP: dict[str, TokenType] = {
    "...": TokenType.ELLIPSIS,
    "===": TokenType.STRICT_EQ,
    "!==": TokenType.STRICT_NEQ,
    ">>>": TokenType.USHR,
    "?.": TokenType.OPTIONAL_CHAIN,
    "=>": TokenType.ARROW,
    "==": TokenType.EQ,
    "!=": TokenType.NEQ,
    "<=": TokenType.LTE,
    ">=": TokenType.GTE,
    "&&": TokenType.AND,
    "||": TokenType.OR,
    "++": TokenType.INCREMENT,
    "--": TokenType.DECREMENT,
    "+=": TokenType.PLUS_ASSIGN,
    "-=": TokenType.MINUS_ASSIGN,
    "*=": TokenType.STAR_ASSIGN,
    "/=": TokenType.SLASH_ASSIGN,
    "%=": TokenType.PERCENT_ASSIGN,
    "<<": TokenType.SHL,
    ">>": TokenType.SHR,
    "+": TokenType.PLUS,
    "-": TokenType.MINUS,
    "*": TokenType.STAR,
    "/": TokenType.SLASH,
    "%": TokenType.PERCENT,
    "=": TokenType.ASSIGN,
    "<": TokenType.LT,
    ">": TokenType.GT,
    "!": TokenType.NOT,
    "&": TokenType.BIT_AND,
    "|": TokenType.BIT_OR,
    "^": TokenType.BIT_XOR,
    "~": TokenType.BIT_NOT,
    "?": TokenType.QUESTION,
    ":": TokenType.COLON,
    ".": TokenType.DOT,
    ",": TokenType.COMMA,
    ";": TokenType.SEMICOLON,
    "(": TokenType.LPAREN,
    ")": TokenType.RPAREN,
    "{": TokenType.LBRACE,
    "}": TokenType.RBRACE,
    "[": TokenType.LBRACKET,
    "]": TokenType.RBRACKET,
    "@": TokenType.AT,
}

_SORTED_OPERATORS = sorted(OPERATOR_MAP, key=len, reverse=True)

_ID_START = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_$")
_ID_PART = _ID_START | set("0123456789")
_HEX_PREFIX = {"x", "X", "b", "B", "o", "O"}
_EXP_CHARS = {"e", "E"}
_SIGN_CHARS = {"+", "-"}
_WHITESPACE = {" ", "\t", "\r", "\n"}


class Lexer:
    """将 ArkTS 源码字符串转换为 Token 序列。"""

    def __init__(self, source: str, filename: str = "<source>") -> None:
        self.source = source
        self.filename = filename
        self.pos = 0
        self.line = 1
        self.col = 1
        self.tokens: list[Token] = []
        self.errors: list[Diagnostic] = []

    # ------------------------------------------------------------ 公共接口
    def tokenize(self) -> list[Token]:
        self.pos, self.line, self.col = 0, 1, 1
        self.tokens, self.errors = [], []

        while not self._at_end():
            ch = self._peek()
            if ch in _WHITESPACE:
                self._advance()
                continue
            if ch == "/" and self._peek(1) == "/":
                self._skip_line_comment()
                continue
            if ch == "/" and self._peek(1) == "*":
                self._skip_block_comment()
                continue
            if ch.isdigit() or (ch == "." and self._peek(1).isdigit()):
                self._read_number()
                continue
            if ch in ("'", '"'):
                self._read_string(ch)
                continue
            if ch == "`":
                self._read_template()
                continue
            if ch in _ID_START:
                self._read_identifier()
                continue
            if self._match_operator():
                continue
            self._error(f"非法字符 {ch!r}")
            self._advance()

        self._emit(TokenType.EOF, "", self.line, self.col)
        return self.tokens

    # ------------------------------------------------------------ 扫描原语
    def _at_end(self) -> bool:
        return self.pos >= len(self.source)

    def _peek(self, offset: int = 0) -> str:
        i = self.pos + offset
        return self.source[i] if i < len(self.source) else ""

    def _advance(self) -> str:
        ch = self.source[self.pos]
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def _emit(self, ttype: TokenType, value: str, line: int, col: int) -> None:
        self.tokens.append(Token(ttype, value, line, col))

    def _error(self, message: str, line: int | None = None, col: int | None = None) -> None:
        self.errors.append(
            Diagnostic(
                message=message,
                line=self.line if line is None else line,
                column=self.col if col is None else col,
                stage="lexer",
                filename=self.filename,
            )
        )

    # ------------------------------------------------------------ 各类词素
    def _skip_line_comment(self) -> None:
        while not self._at_end() and self._peek() != "\n":
            self._advance()

    def _skip_block_comment(self) -> None:
        line, col = self.line, self.col
        self._advance()
        self._advance()
        while not self._at_end():
            if self._peek() == "*" and self._peek(1) == "/":
                self._advance()
                self._advance()
                return
            self._advance()
        self._error("未闭合的块注释", line, col)

    def _read_number(self) -> None:
        start, line, col = self.pos, self.line, self.col
        if self._peek() == "0" and self._peek(1) in _HEX_PREFIX:
            self._advance()
            self._advance()
            digits = ""
            while not self._at_end() and (self._peek().isalnum() or self._peek() == "_"):
                digits += self._advance()
            if not digits:
                self._error("进制字面量缺少数字位", line, col)
            self._emit(TokenType.NUMBER, self.source[start : self.pos], line, col)
            return

        seen_dot = False
        seen_exp = False
        while not self._at_end():
            ch = self._peek()
            if ch.isdigit() or ch == "_":
                self._advance()
            elif ch == "." and not seen_dot and not seen_exp:
                if self._peek(1) == ".":
                    break
                seen_dot = True
                self._advance()
            elif ch in _EXP_CHARS and not seen_exp:
                nxt = self._peek(1)
                if nxt.isdigit() or (nxt in _SIGN_CHARS and self._peek(2).isdigit()):
                    seen_exp = True
                    self._advance()
                    if self._peek() in _SIGN_CHARS:
                        self._advance()
                else:
                    break
            else:
                break
        self._emit(TokenType.NUMBER, self.source[start : self.pos], line, col)

    def _read_string(self, quote: str) -> None:
        start, line, col = self.pos, self.line, self.col
        self._advance()
        terminated = False
        while not self._at_end():
            ch = self._peek()
            if ch == "\\":
                self._advance()
                if self._at_end():
                    break
                self._advance()
                continue
            if ch == quote:
                self._advance()
                terminated = True
                break
            if ch == "\n":
                break
            self._advance()
        if not terminated:
            self._error("未闭合的字符串字面量", line, col)
        self._emit(TokenType.STRING, self.source[start : self.pos], line, col)

    def _read_template(self) -> None:
        start, line, col = self.pos, self.line, self.col
        self._advance()
        depth = 0
        terminated = False
        while not self._at_end():
            ch = self._peek()
            if ch == "\\":
                self._advance()
                if not self._at_end():
                    self._advance()
                continue
            if ch == "$" and self._peek(1) == "{":
                depth += 1
                self._advance()
                self._advance()
                continue
            if ch == "}" and depth > 0:
                depth -= 1
            elif ch == "`" and depth == 0:
                self._advance()
                terminated = True
                break
            self._advance()
        if not terminated:
            self._error("未闭合的模板字符串", line, col)
        self._emit(TokenType.TEMPLATE_STRING, self.source[start : self.pos], line, col)

    def _read_identifier(self) -> None:
        start, line, col = self.pos, self.line, self.col
        while not self._at_end() and self._peek() in _ID_PART:
            self._advance()
        text = self.source[start : self.pos]
        self._emit(KEYWORDS.get(text, TokenType.IDENTIFIER), text, line, col)

    def _match_operator(self) -> bool:
        for op in _SORTED_OPERATORS:
            if self.source.startswith(op, self.pos):
                line, col = self.line, self.col
                for _ in range(len(op)):
                    self._advance()
                self._emit(OPERATOR_MAP[op], op, line, col)
                return True
        return False


def tokenize(source: str, filename: str = "<source>") -> tuple[list[Token], list[Diagnostic]]:
    """便捷函数：返回 ``(tokens, errors)``。"""
    lexer = Lexer(source, filename)
    tokens = lexer.tokenize()
    return tokens, lexer.errors