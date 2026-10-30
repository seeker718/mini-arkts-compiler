"""统一的诊断信息类型。

词法分析、语法分析（后续语义分析）都复用同一个 :class:`Diagnostic`，
这样错误既可以直接打印，也能被自动化测试脚本结构化解析（实验四需要）。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Diagnostic:
    """一条错误/警告信息。

    Attributes:
        message:  人类可读的描述。
        line:     1 起始的行号。
        column:   1 起始的列号。
        severity: ``error`` 或 ``warning``。
        stage:    产生该诊断的阶段：``lexer`` / ``parser`` / ``sema`` / ``codegen``。
        filename: 源文件名，便于多文件场景定位。
    """

    message: str
    line: int = 0
    column: int = 0
    severity: str = "error"
    stage: str = ""
    filename: str = "<source>"

    def __str__(self) -> str:
        prefix = f"{self.filename}:{self.line}:{self.column}"
        return f"{prefix}: {self.severity}: {self.message}"

    def to_dict(self) -> dict:
        return {
            "message": self.message,
            "line": self.line,
            "column": self.column,
            "severity": self.severity,
            "stage": self.stage,
            "filename": self.filename,
        }