"""ArkTS 子集递归下降语法分析器（实验一）。

文法概要（EBNF，已消除左递归）::

    program        = statement* ;
    statement      = block | varDecl | funcDecl | typeDecl | ifStmt | whileStmt
                   | doWhileStmt | forStmt | returnStmt | breakStmt | continueStmt
                   | expressionStmt ;
    block          = "{" statement* "}" ;
    varDecl        = ("let"|"const"|"var") IDENT typeAnno? ("=" expr)? ";" ;
    funcDecl       = "function" IDENT "(" params? ")" typeAnno? block ;
    typeDecl       = decorator* ("class"|"struct"|"interface") IDENT
                     ("extends" IDENT)? ("implements" typeList)? "{" member* "}" ;
    member         = decorator* modifier* ( methodDecl | fieldDecl ) ;
    methodDecl     = IDENT "(" params? ")" typeAnno? block ;
    fieldDecl      = IDENT typeAnno? ("=" expr)? ";" ;
    expressionStmt = expr ( "{" statement* "}" )? ";"? ;   // 尾随块 => UiContainer

鸿蒙特有语法（相对 TypeScript 的扩展）：
* 装饰器 ``@Entry`` / ``@Component`` / ``@State`` ...
* ``struct`` 组件声明 + ``build()`` 方法
* 声明式 UI：``Column() { Text('hi') }`` 这种「调用 + 尾随块」结构，
  在 :class:`compiler.ast_nodes.UiContainer` 中统一表示。

错误恢复采用「恐慌模式 + 同步集」：单条语句出错后跳到下一个语句起始符，
从而一次编译能报出多个错误。
"""

from __future__ import annotations

from .ast_nodes import (
    ArrayLiteral,
    ArrowFunctionExpression,
    AssignmentExpression,
    BinaryExpression,
    Block,
    BreakStatement,
    CallExpression,
    ClassDeclaration,
    ConditionalExpression,
    ContinueStatement,
    Decorator,
    DoWhileStatement,
    ExpressionStatement,
    FieldDeclaration,
    ForStatement,
    FunctionDeclaration,
    Identifier,
    IfStatement,
    Literal,
    LogicalExpression,
    MemberExpression,
    MethodDeclaration,
    NewExpression,
    ObjectLiteral,
    Parameter,
    Program,
    Property,
    ReturnStatement,
    SuperExpression,
    ThisExpression,
    TypeAnnotation,
    UiContainer,
    UnaryExpression,
    UpdateExpression,
    VariableDeclaration,
    WhileStatement,
)
from .diagnostics import Diagnostic
from .tokens import Token, TokenType

T = TokenType

# 赋值类运算符
_ASSIGN_OPS = {T.ASSIGN, T.PLUS_ASSIGN, T.MINUS_ASSIGN, T.STAR_ASSIGN, T.SLASH_ASSIGN, T.PERCENT_ASSIGN}
# 一元前缀运算符
_UNARY_PREFIX_OPS = {T.NOT, T.BIT_NOT, T.PLUS, T.MINUS, T.TYPEOF, T.VOID, T.AWAIT}
# 作用域修饰符
_MODIFIERS = {T.PUBLIC, T.PRIVATE, T.PROTECTED, T.STATIC, T.READONLY, T.ASYNC}
# 可作为类型名的词法单元
_TYPE_KEYWORDS = {T.NUMBER_TYPE, T.STRING_TYPE, T.BOOLEAN_TYPE, T.VOID, T.ANY_TYPE, T.NEVER_TYPE}
# 语句同步集（错误恢复时在此处停下）
_STATEMENT_START = {
    T.LET, T.CONST, T.VAR, T.FUNCTION, T.CLASS, T.STRUCT, T.INTERFACE,
    T.IF, T.WHILE, T.DO, T.FOR, T.RETURN, T.BREAK, T.CONTINUE, T.LBRACE, T.AT,
}
_SYNC_STOP = _STATEMENT_START | {T.SEMICOLON, T.RBRACE, T.EOF}


class ParseError(Exception):
    """内部使用：携带一条诊断信息，由 statement 级别捕获。"""

    def __init__(self, diagnostic: Diagnostic) -> None:
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


class Parser:
    def __init__(self, tokens: list[Token], filename: str = "<source>") -> None:
        self.tokens = tokens
        self.filename = filename
        self.pos = 0
        self.errors: list[Diagnostic] = []
        # > 0 表示正处于声明式 UI 块（build() / @Builder）中，
        # 此时组件语句允许省略分号。
        self.ui_depth = 0

    # ------------------------------------------------------------ 顶层
    def parse(self) -> Program:
        body = []
        while not self._at(T.EOF):
            stmt = self._statement()
            if stmt is not None:
                body.append(stmt)
        return Program(body=body, lineno=1, col=1)

    # ------------------------------------------------------------ 游标工具
    def _current(self) -> Token:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else self.tokens[-1]

    def _peek(self, offset: int = 1) -> Token:
        i = min(self.pos + offset, len(self.tokens) - 1)
        return self.tokens[i]

    def _at(self, *types: TokenType) -> bool:
        return self._current().type in types

    def _advance(self) -> Token:
        tok = self._current()
        if tok.type is not T.EOF:
            self.pos += 1
        return tok

    def _match(self, *types: TokenType) -> bool:
        if self._at(*types):
            self._advance()
            return True
        return False

    def _describe(self, token: Token) -> str:
        if token.type is T.EOF:
            return "文件结尾"
        return f"'{token.value}'"

    def _raise(self, message: str, token: Token | None = None) -> None:
        tok = token or self._current()
        raise ParseError(
            Diagnostic(message, tok.line, tok.column, "error", "parser", self.filename)
        )

    def _expect(self, ttype: TokenType, what: str) -> Token:
        if self._at(ttype):
            return self._advance()
        self._raise(f"期望{what}，但遇到 {self._describe(self._current())}")

    def _expect_semicolon(self) -> None:
        if self._match(T.SEMICOLON):
            return
        if self._at(T.RBRACE, T.EOF):
            return
        self._raise(f"缺少分号 ';'，但遇到 {self._describe(self._current())}")

    def _synchronize(self) -> None:
        # 若当前位置已经是新语句的起点，直接交给上层继续解析，
        # 否则会把下一条合法语句一起吞掉。
        if self._at(*_STATEMENT_START):
            return
        if self._at(T.EOF):
            return
        if self._at(T.SEMICOLON, T.RBRACE):
            self._advance()
            return
        while not self._at(T.EOF):
            self._advance()
            if self._at(*_SYNC_STOP):
                if self._at(T.SEMICOLON, T.RBRACE):
                    self._advance()
                return

    # ------------------------------------------------------------ 语句
    def _statement(self):
        start = self.pos
        try:
            return self._statement_inner()
        except ParseError as exc:
            self.errors.append(exc.diagnostic)
            self._synchronize()
            if self.pos == start:      # 保底：任何情况下都必须前进，避免死循环
                self._advance()
            return None

    def _statement_inner(self):
        t = self._current()
        if t.type is T.LBRACE:
            return self._block()
        if t.type in (T.LET, T.CONST, T.VAR):
            return self._variable_declaration()
        if t.type is T.FUNCTION:
            return self._function_declaration()
        if t.type in (T.CLASS, T.STRUCT, T.INTERFACE):
            return self._type_declaration(decorators=[], modifiers=[])
        if t.type is T.IF:
            return self._if_statement()
        if t.type is T.WHILE:
            return self._while_statement()
        if t.type is T.DO:
            return self._do_while_statement()
        if t.type is T.FOR:
            return self._for_statement()
        if t.type is T.RETURN:
            return self._return_statement()
        if t.type is T.BREAK:
            tok = self._advance()
            self._expect_semicolon()
            return BreakStatement(lineno=tok.line, col=tok.column)
        if t.type is T.CONTINUE:
            tok = self._advance()
            self._expect_semicolon()
            return ContinueStatement(lineno=tok.line, col=tok.column)
        if t.type is T.AT:
            decorators = self._decorators()
            if self._at(T.CLASS, T.STRUCT, T.INTERFACE):
                return self._type_declaration(decorators=decorators, modifiers=[])
            self._raise("装饰器只能修饰 class / struct / interface / 成员")
        if t.type in (T.IMPORT, T.EXPORT):
            self._skip_to_semicolon()
            return None
        return self._expression_statement()

    def _skip_to_semicolon(self) -> None:
        while not self._at(T.EOF, T.SEMICOLON):
            self._advance()
        self._match(T.SEMICOLON)

    def _block(self) -> Block:
        tok = self._expect(T.LBRACE, "'{'")
        body = []
        while not self._at(T.RBRACE, T.EOF):
            stmt = self._statement()
            if stmt is not None:
                body.append(stmt)
        self._expect(T.RBRACE, "'}'")
        return Block(body=body, lineno=tok.line, col=tok.column)

    def _block_ui(self) -> Block:
        """解析声明式 UI 块（build() / @Builder），其中组件语句允许省略分号。"""
        self.ui_depth += 1
        try:
            return self._block()
        finally:
            self.ui_depth -= 1

    def _variable_declaration(self, require_semicolon: bool = True) -> VariableDeclaration:
        kw = self._advance()
        name = self._expect(T.IDENTIFIER, "变量名")
        type_annotation = self._type_annotation_optional()
        init = None
        if self._match(T.ASSIGN):
            init = self._expression()
        if require_semicolon:
            self._expect_semicolon()
        return VariableDeclaration(
            kind=kw.value,
            name=name.value,
            type_annotation=type_annotation,
            init=init,
            lineno=kw.line,
            col=kw.column,
        )

    def _function_declaration(self, decorators=None, modifiers=None) -> FunctionDeclaration:
        kw = self._expect(T.FUNCTION, "'function'")
        name = self._expect(T.IDENTIFIER, "函数名")
        params = self._parameters()
        return_type = self._type_annotation_optional()
        body = self._block()
        return FunctionDeclaration(
            name=name.value,
            params=params,
            return_type=return_type,
            body=body,
            decorators=decorators or [],
            modifiers=modifiers or [],
            lineno=kw.line,
            col=kw.column,
        )

    def _type_declaration(self, decorators, modifiers) -> ClassDeclaration:
        kw = self._advance()
        kind = kw.value
        name = self._expect(T.IDENTIFIER, "类型名")
        extends = None
        implements: list[str] = []
        if self._match(T.EXTENDS):
            extends = self._expect(T.IDENTIFIER, "父类型名").value
        if self._match(T.IMPLEMENTS):
            implements.append(self._expect(T.IDENTIFIER, "接口名").value)
            while self._match(T.COMMA):
                implements.append(self._expect(T.IDENTIFIER, "接口名").value)
        self._expect(T.LBRACE, "'{'")
        members = []
        while not self._at(T.RBRACE, T.EOF):
            member = self._class_member()
            if member is not None:
                members.append(member)
        self._expect(T.RBRACE, "'}'")
        return ClassDeclaration(
            kind=kind,
            name=name.value,
            extends=extends,
            implements=implements,
            members=members,
            decorators=decorators,
            lineno=kw.line,
            col=kw.column,
        )

    def _class_member(self):
        start = self.pos
        try:
            return self._class_member_inner()
        except ParseError as exc:
            self.errors.append(exc.diagnostic)
            self._synchronize()
            if self.pos == start:      # 保底：类成员解析失败后也必须前进
                self._advance()
            return None

    def _class_member_inner(self):
        decorators = self._decorators() if self._at(T.AT) else []
        modifiers: list[str] = []
        while self._at(*_MODIFIERS):
            modifiers.append(self._advance().value)
        name = self._expect(T.IDENTIFIER, "成员名")
        if self._at(T.LPAREN):
            params = self._parameters()
            return_type = self._type_annotation_optional()
            if self._at(T.LBRACE):
                is_ui = name.value == "build" or any(d.name == "Builder" for d in decorators)
                body = self._block_ui() if is_ui else self._block()
            else:
                # 接口中的方法签名：只有声明，没有方法体
                self._expect_semicolon()
                body = None
            return MethodDeclaration(
                name=name.value,
                params=params,
                return_type=return_type,
                body=body,
                decorators=decorators,
                modifiers=modifiers,
                lineno=name.line,
                col=name.column,
            )
        type_annotation = self._type_annotation_optional()
        init = None
        if self._match(T.ASSIGN):
            init = self._expression()
        self._expect_semicolon()
        return FieldDeclaration(
            name=name.value,
            type_annotation=type_annotation,
            init=init,
            decorators=decorators,
            modifiers=modifiers,
            lineno=name.line,
            col=name.column,
        )

    def _decorators(self) -> list[Decorator]:
        result = []
        while self._at(T.AT):
            at_tok = self._advance()
            name = self._expect(T.IDENTIFIER, "装饰器名")
            args = []
            if self._at(T.LPAREN):
                args = self._arguments()
            result.append(
                Decorator(name=name.value, arguments=args, lineno=at_tok.line, col=at_tok.column)
            )
        return result

    def _if_statement(self) -> IfStatement:
        kw = self._advance()
        test = self._parenthesized_expression()
        consequent = self._statement()
        alternate = self._statement() if self._match(T.ELSE) else None
        return IfStatement(
            test=test, consequent=consequent, alternate=alternate, lineno=kw.line, col=kw.column
        )

    def _while_statement(self) -> WhileStatement:
        kw = self._advance()
        test = self._parenthesized_expression()
        body = self._statement()
        return WhileStatement(test=test, body=body, lineno=kw.line, col=kw.column)

    def _do_while_statement(self) -> DoWhileStatement:
        kw = self._advance()
        body = self._statement()
        self._expect(T.WHILE, "'while'")
        test = self._parenthesized_expression()
        self._expect_semicolon()
        return DoWhileStatement(body=body, test=test, lineno=kw.line, col=kw.column)

    def _for_statement(self) -> ForStatement:
        kw = self._advance()
        self._expect(T.LPAREN, "'('")
        init = None
        if not self._at(T.SEMICOLON):
            if self._at(T.LET, T.CONST, T.VAR):
                init = self._variable_declaration(require_semicolon=False)
            else:
                init = self._expression()
        self._expect(T.SEMICOLON, "';'")
        test = None if self._at(T.SEMICOLON) else self._expression()
        self._expect(T.SEMICOLON, "';'")
        update = None if self._at(T.RPAREN) else self._expression()
        self._expect(T.RPAREN, "')'")
        body = self._statement()
        return ForStatement(
            init=init, test=test, update=update, body=body, lineno=kw.line, col=kw.column
        )

    def _return_statement(self) -> ReturnStatement:
        kw = self._advance()
        argument = None
        if not self._at(T.SEMICOLON, T.RBRACE, T.EOF):
            argument = self._expression()
        self._expect_semicolon()
        return ReturnStatement(argument=argument, lineno=kw.line, col=kw.column)

    def _expression_statement(self):
        expr = self._expression()
        if self._at(T.LBRACE) and isinstance(expr, CallExpression):
            return self._ui_container(expr)
        if self.ui_depth > 0 and _is_ui_element(expr):
            self._match(T.SEMICOLON)
            return ExpressionStatement(expression=expr, lineno=expr.lineno, col=expr.col)
        self._expect_semicolon()
        return ExpressionStatement(expression=expr, lineno=expr.lineno, col=expr.col)

    def _ui_container(self, call: CallExpression) -> UiContainer:
        callee = call.callee
        name = callee.name if isinstance(callee, Identifier) else "<expr>"
        block = self._block()
        self._match(T.SEMICOLON)
        return UiContainer(
            name=name,
            arguments=call.arguments,
            children=block.body,
            lineno=call.lineno,
            col=call.col,
        )

    # ------------------------------------------------------------ 参数与类型
    def _parameters(self) -> list[Parameter]:
        self._expect(T.LPAREN, "'('")
        params: list[Parameter] = []
        if not self._at(T.RPAREN):
            params.append(self._parameter())
            while self._match(T.COMMA):
                if self._at(T.RPAREN):
                    break
                params.append(self._parameter())
        self._expect(T.RPAREN, "')'")
        return params

    def _parameter(self) -> Parameter:
        tok = self._current()
        rest = self._match(T.ELLIPSIS)
        name = self._expect(T.IDENTIFIER, "参数名")
        type_annotation = self._type_annotation_optional()
        default = None
        if self._match(T.ASSIGN):
            default = self._assignment_expression()
        return Parameter(
            name=name.value,
            type_annotation=type_annotation,
            default=default,
            rest=rest,
            lineno=tok.line,
            col=tok.column,
        )

    def _type_annotation_optional(self) -> TypeAnnotation | None:
        if self._match(T.COLON):
            return self._type_annotation()
        return None

    def _type_annotation(self) -> TypeAnnotation:
        tok = self._current()
        if tok.type in _TYPE_KEYWORDS or tok.type is T.IDENTIFIER:
            name = self._advance().value
        else:
            self._raise(f"期望类型名，但遇到 {self._describe(tok)}")
        type_args: list[TypeAnnotation] = []
        if self._match(T.LT):
            type_args.append(self._type_annotation())
            while self._match(T.COMMA):
                type_args.append(self._type_annotation())
            self._expect(T.GT, "'>'")
        is_array = False
        if self._at(T.LBRACKET) and self._peek(1).type is T.RBRACKET:
            self._advance()
            self._advance()
            is_array = True
        return TypeAnnotation(
            name=name, type_args=type_args, is_array=is_array, lineno=tok.line, col=tok.column
        )

    # ------------------------------------------------------------ 表达式
    def _expression(self):
        return self._assignment_expression()

    def _parenthesized_expression(self):
        self._expect(T.LPAREN, "'('")
        expr = self._expression()
        self._expect(T.RPAREN, "')'")
        return expr

    def _assignment_expression(self):
        left = self._conditional_expression()
        if self._current().type in _ASSIGN_OPS:
            op = self._advance()
            right = self._assignment_expression()
            return AssignmentExpression(
                operator=op.value, left=left, right=right, lineno=left.lineno, col=left.col
            )
        return left

    def _conditional_expression(self):
        test = self._logical_or()
        if self._match(T.QUESTION):
            consequent = self._assignment_expression()
            self._expect(T.COLON, "':'")
            alternate = self._assignment_expression()
            return ConditionalExpression(
                test=test, consequent=consequent, alternate=alternate,
                lineno=test.lineno, col=test.col,
            )
        return test

    def _binary(self, next_level, op_types, node_cls):
        left = next_level()
        while self._current().type in op_types:
            op = self._advance()
            right = next_level()
            left = node_cls(
                operator=op.value, left=left, right=right, lineno=left.lineno, col=left.col
            )
        return left

    def _logical_or(self):
        return self._binary(self._logical_and, {T.OR}, LogicalExpression)

    def _logical_and(self):
        return self._binary(self._bit_or, {T.AND}, LogicalExpression)

    def _bit_or(self):
        return self._binary(self._bit_xor, {T.BIT_OR}, BinaryExpression)

    def _bit_xor(self):
        return self._binary(self._bit_and, {T.BIT_XOR}, BinaryExpression)

    def _bit_and(self):
        return self._binary(self._equality, {T.BIT_AND}, BinaryExpression)

    def _equality(self):
        return self._binary(
            self._relational, {T.EQ, T.NEQ, T.STRICT_EQ, T.STRICT_NEQ}, BinaryExpression
        )

    def _relational(self):
        return self._binary(self._shift, {T.LT, T.GT, T.LTE, T.GTE, T.INSTANCEOF, T.IN}, BinaryExpression)

    def _shift(self):
        return self._binary(self._additive, {T.SHL, T.SHR, T.USHR}, BinaryExpression)

    def _additive(self):
        return self._binary(self._multiplicative, {T.PLUS, T.MINUS}, BinaryExpression)

    def _multiplicative(self):
        return self._binary(self._unary, {T.STAR, T.SLASH, T.PERCENT}, BinaryExpression)

    def _unary(self):
        tok = self._current()
        if tok.type in _UNARY_PREFIX_OPS:
            self._advance()
            operand = self._unary()
            return UnaryExpression(
                operator=tok.value, operand=operand, prefix=True, lineno=tok.line, col=tok.column
            )
        if tok.type in (T.INCREMENT, T.DECREMENT):
            self._advance()
            operand = self._unary()
            return UpdateExpression(
                operator=tok.value, argument=operand, prefix=True, lineno=tok.line, col=tok.column
            )
        return self._postfix()

    def _postfix(self):
        expr = self._primary()
        while True:
            tok = self._current()
            if tok.type in (T.DOT, T.OPTIONAL_CHAIN):
                self._advance()
                prop = self._expect(T.IDENTIFIER, "属性名")
                expr = MemberExpression(
                    object=expr,
                    property=Identifier(name=prop.value, lineno=prop.line, col=prop.column),
                    computed=False,
                    lineno=expr.lineno,
                    col=expr.col,
                )
            elif tok.type is T.LBRACKET:
                self._advance()
                index = self._expression()
                self._expect(T.RBRACKET, "']'")
                expr = MemberExpression(
                    object=expr, property=index, computed=True, lineno=expr.lineno, col=expr.col
                )
            elif tok.type is T.LPAREN:
                args = self._arguments()
                expr = CallExpression(
                    callee=expr, arguments=args, lineno=expr.lineno, col=expr.col
                )
            elif tok.type in (T.INCREMENT, T.DECREMENT):
                self._advance()
                expr = UpdateExpression(
                    operator=tok.value, argument=expr, prefix=False,
                    lineno=expr.lineno, col=expr.col,
                )
            else:
                break
        return expr

    def _primary(self):
        tok = self._current()
        if tok.type is T.NUMBER:
            self._advance()
            return Literal(value=_parse_number(tok.value), raw=tok.value,
                           literal_type="number", lineno=tok.line, col=tok.column)
        if tok.type is T.STRING:
            self._advance()
            return Literal(value=_unquote(tok.value), raw=tok.value,
                           literal_type="string", lineno=tok.line, col=tok.column)
        if tok.type is T.TEMPLATE_STRING:
            self._advance()
            return Literal(value=tok.value, raw=tok.value,
                           literal_type="template", lineno=tok.line, col=tok.column)
        if tok.type in (T.TRUE, T.FALSE):
            self._advance()
            return Literal(value=tok.type is T.TRUE, raw=tok.value,
                           literal_type="boolean", lineno=tok.line, col=tok.column)
        if tok.type is T.NULL:
            self._advance()
            return Literal(value=None, raw=tok.value, literal_type="null",
                           lineno=tok.line, col=tok.column)
        if tok.type is T.UNDEFINED:
            self._advance()
            return Literal(value=None, raw=tok.value, literal_type="undefined",
                           lineno=tok.line, col=tok.column)
        if tok.type is T.THIS:
            self._advance()
            return ThisExpression(lineno=tok.line, col=tok.column)
        if tok.type is T.SUPER:
            self._advance()
            return SuperExpression(lineno=tok.line, col=tok.column)
        if tok.type is T.NEW:
            return self._new_expression()
        if tok.type is T.IDENTIFIER:
            if self._peek(1).type is T.ARROW:
                self._advance()
                self._advance()
                body, is_expr = self._arrow_body()
                param = Parameter(name=tok.value, lineno=tok.line, col=tok.column)
                return ArrowFunctionExpression(
                    params=[param], body=body, is_expression=is_expr,
                    lineno=tok.line, col=tok.column,
                )
            self._advance()
            return Identifier(name=tok.value, lineno=tok.line, col=tok.column)
        if tok.type is T.LPAREN:
            if self._looks_like_arrow_params():
                params = self._parameters()
                self._expect(T.ARROW, "'=>'")
                body, is_expr = self._arrow_body()
                return ArrowFunctionExpression(
                    params=params, body=body, is_expression=is_expr,
                    lineno=tok.line, col=tok.column,
                )
            self._advance()
            expr = self._expression()
            self._expect(T.RPAREN, "')'")
            return expr
        if tok.type is T.LBRACKET:
            return self._array_literal()
        if tok.type is T.LBRACE:
            return self._object_literal()
        self._raise(f"意外的 {self._describe(tok)}")

    def _new_expression(self) -> NewExpression:
        tok = self._expect(T.NEW, "'new'")
        callee = self._postfix_callee()
        args = self._arguments() if self._at(T.LPAREN) else []
        return NewExpression(callee=callee, arguments=args, lineno=tok.line, col=tok.column)

    def _postfix_callee(self):
        tok = self._expect(T.IDENTIFIER, "构造函数名")
        expr = Identifier(name=tok.value, lineno=tok.line, col=tok.column)
        while self._at(T.DOT):
            self._advance()
            prop = self._expect(T.IDENTIFIER, "属性名")
            expr = MemberExpression(
                object=expr,
                property=Identifier(name=prop.value, lineno=prop.line, col=prop.column),
                computed=False,
            )
        return expr

    def _arrow_body(self):
        if self._at(T.LBRACE):
            return self._block(), False
        return self._assignment_expression(), True

    def _arguments(self) -> list:
        self._expect(T.LPAREN, "'('")
        args = []
        if not self._at(T.RPAREN):
            args.append(self._assignment_expression())
            while self._match(T.COMMA):
                if self._at(T.RPAREN):
                    break
                args.append(self._assignment_expression())
        self._expect(T.RPAREN, "')'")
        return args

    def _array_literal(self) -> ArrayLiteral:
        tok = self._expect(T.LBRACKET, "'['")
        elements = []
        while not self._at(T.RBRACKET, T.EOF):
            elements.append(self._assignment_expression())
            if not self._match(T.COMMA):
                break
        self._expect(T.RBRACKET, "']'")
        return ArrayLiteral(elements=elements, lineno=tok.line, col=tok.column)

    def _object_literal(self) -> ObjectLiteral:
        tok = self._expect(T.LBRACE, "'{'")
        properties = []
        while not self._at(T.RBRACE, T.EOF):
            key = self._property_key()
            if self._match(T.COLON):
                value = self._assignment_expression()
                properties.append(Property(key=key, value=value, lineno=key.lineno, col=key.col))
            else:
                properties.append(
                    Property(key=key, value=key, shorthand=True, lineno=key.lineno, col=key.col)
                )
            if not self._match(T.COMMA):
                break
        self._expect(T.RBRACE, "'}'")
        return ObjectLiteral(properties=properties, lineno=tok.line, col=tok.column)

    def _property_key(self):
        tok = self._current()
        if tok.type is T.STRING:
            self._advance()
            return Literal(value=_unquote(tok.value), raw=tok.value, literal_type="string",
                           lineno=tok.line, col=tok.column)
        if tok.type is T.NUMBER:
            self._advance()
            return Literal(value=_parse_number(tok.value), raw=tok.value, literal_type="number",
                           lineno=tok.line, col=tok.column)
        if tok.type is T.IDENTIFIER or tok.type.name.endswith("_TYPE") or tok.type is T.DEFAULT:
            self._advance()
            return Identifier(name=tok.value, lineno=tok.line, col=tok.column)
        self._raise(f"非法的对象属性名 {self._describe(tok)}")

    def _looks_like_arrow_params(self) -> bool:
        depth = 0
        i = self.pos
        while i < len(self.tokens):
            tt = self.tokens[i].type
            if tt is T.LPAREN:
                depth += 1
            elif tt is T.RPAREN:
                depth -= 1
                if depth == 0:
                    j = i + 1
                    return j < len(self.tokens) and self.tokens[j].type is T.ARROW
            elif tt is T.EOF:
                return False
            i += 1
        return False


def _is_ui_element(node) -> bool:
    """判断表达式是否为声明式 UI 组件调用（含 ``Text(..).fontSize(..)`` 链式形态）。"""
    if isinstance(node, CallExpression):
        return True
    if isinstance(node, MemberExpression):
        return _is_ui_element(node.object)
    return False


# ---------------------------------------------------------------- 字面量解析
def _parse_number(raw: str) -> float | int:
    text = raw.replace("_", "")
    lower = text.lower()
    if lower.startswith("0x"):
        return int(lower, 16)
    if lower.startswith("0b"):
        return int(lower, 2)
    if lower.startswith("0o"):
        return int(lower, 8)
    if "." in text or "e" in lower:
        return float(text)
    return int(text)


_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", "'": "'", '"': '"', "0": "\0"}


def _unquote(raw: str) -> str:
    if len(raw) < 2:
        return raw
    body = raw[1:-1]
    out = []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == "\\" and i + 1 < len(body):
            out.append(_ESCAPES.get(body[i + 1], body[i + 1]))
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def parse(tokens: list[Token], filename: str = "<source>") -> tuple[Program, list[Diagnostic]]:
    """便捷函数：返回 ``(ast, errors)``。"""
    parser = Parser(tokens, filename)
    program = parser.parse()
    return program, parser.errors