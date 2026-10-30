"""编译器前端模糊测试器（实验四）。

由四个模块组成：

    GrammarFuzzer  —— 基于语法的用例生成：按 ArkTS 子集文法随机产出**合法**代码片段；
    Mutator        —— 变异生成：对合法 / 非法种子做位翻转、插入、删除、关键字替换等；
    FrontendRunner —— 测试驱动：把用例喂给「词法 → 语法 → 语义 → IR」整条前端，
                      捕获未处理异常（崩溃）与超时；
    FuzzReport     —— 结果收集、按异常类型与消息去重、分类统计。

所有随机过程都由种子控制，因此任何一次「发现崩溃」都能用同一种子复现。
"""

from __future__ import annotations

import pathlib
import random
import time
import traceback
from dataclasses import dataclass, field

from . import irgen
from .lexer import tokenize
from .parser import parse
from .sema import analyze


# ================================================================ 用例与结果
@dataclass
class FuzzCase:
    id: int
    source: str
    strategy: str          # grammar / mutate
    origin: str = ""

    def preview(self, width: int = 60) -> str:
        text = " ".join(self.source.split())
        return text[:width] + ("…" if len(text) > width else "")


@dataclass
class FuzzResult:
    case: FuzzCase
    outcome: str           # ok / diagnostics / crash / timeout
    error_type: str = ""
    message: str = ""
    elapsed_ms: float = 0.0
    detail: str = ""

    @property
    def fingerprint(self) -> tuple:
        """去重指纹：按异常类型 + 消息前 80 字符归并同类问题。"""
        if self.outcome == "crash":
            return (self.error_type, self.message[:80])
        if self.outcome == "timeout":
            return ("Timeout", "超过时间阈值")
        return (self.outcome, "")


@dataclass
class FuzzReport:
    cases: list = field(default_factory=list)
    results: list = field(default_factory=list)

    def stats(self) -> dict:
        counts = {"ok": 0, "diagnostics": 0, "crash": 0, "timeout": 0}
        for result in self.results:
            counts[result.outcome] = counts.get(result.outcome, 0) + 1
        return {
            "total": len(self.results),
            "ok": counts["ok"],
            "diagnostics": counts["diagnostics"],
            "crash": counts["crash"],
            "timeout": counts["timeout"],
            "unique_crashes": len(self.crash_groups()),
        }

    def crash_groups(self) -> dict:
        groups: dict[tuple, list] = {}
        for result in self.results:
            if result.outcome in ("crash", "timeout"):
                groups.setdefault(result.fingerprint, []).append(result)
        return groups

    def to_text(self, max_groups: int = 8) -> str:
        stats = self.stats()
        lines = [
            "模糊测试报告", "=" * 56,
            f"  用例总数    : {stats['total']}",
            f"  正常通过    : {stats['ok']}",
            f"  诊断(未崩溃): {stats['diagnostics']}",
            f"  崩溃        : {stats['crash']}",
            f"  超时        : {stats['timeout']}",
            f"  去重后崩溃组: {stats['unique_crashes']}",
        ]
        groups = self.crash_groups()
        if groups:
            lines += ["", "异常分类（按去重指纹）", "-" * 56]
            for (etype, msg), items in sorted(groups.items(), key=lambda kv: -len(kv[1]))[:max_groups]:
                lines.append(f"  [{etype}] 出现 {len(items)} 次：{msg}")
                first = items[0]
                lines.append(f"      复现用例 #{first.case.id}：{first.case.preview(70)}")
        else:
            lines += ["", "未发现崩溃或超时（前端在该轮测试中保持健壮）"]
        return "\n".join(lines)


# ================================================================ 语法生成
class GrammarFuzzer:
    """按文法随机生成合法的 ArkTS 子集片段。"""

    def __init__(self, seed: int = 0) -> None:
        self.rnd = random.Random(seed)
        self.vars: list[str] = []
        self._decl_counter = 0

    def generate(self) -> str:
        functions = []
        for i in range(self.rnd.randint(1, 3)):
            functions.append(self._function(f"fn{i}"))
        return "\n\n".join(functions)

    # ---------------------------------------------------------- 片段
    def _function(self, name: str) -> str:
        self.vars = [f"v{i}" for i in range(self.rnd.randint(1, 3))]
        self._decl_counter = 0
        lines = []
        for var in self.vars:
            lines.append(f"  let {var}: number = {self.rnd.randint(0, 20)};")
        for _ in range(self.rnd.randint(1, 4)):
            lines.append("  " + self._stmt())
        lines.append(f"  return {self._num_expr()};")
        return f"function {name}(): number {{\n" + "\n".join(lines) + "\n}"

    def _stmt(self, depth: int = 0) -> str:
        kind = self.rnd.randint(0, 5)
        if depth >= 1:
            kind = self.rnd.randint(0, 1)
        if kind == 0:
            return f"{self.rnd.choice(self.vars)} = {self._num_expr()};"
        if kind == 1:
            # 新声明必须用全新的变量名，否则会在同一作用域内重复声明
            self._decl_counter += 1
            return f"let d{self._decl_counter}: number = {self._num_expr()};"
        if kind == 2:
            body = self._stmt(depth + 1)
            alt = self._stmt(depth + 1)
            return f"if ({self._bool_expr()}) {{ {body} }} else {{ {alt} }}"
        if kind == 3:
            return f"if ({self._bool_expr()}) {{ {self._stmt(depth + 1)} }}"
        if kind == 4:
            return (f"while ({self._bool_expr()}) {{ "
                    f"{self.rnd.choice(self.vars)} = {self.rnd.choice(self.vars)} + 1; }}")
        return (f"for (let i: number = 0; i < {self.rnd.randint(1, 5)}; i++) {{ "
                f"{self.rnd.choice(self.vars)} = {self.rnd.choice(self.vars)} + 1; }}")

    def _num_expr(self, depth: int = 0) -> str:
        if depth >= 2 or self.rnd.random() < 0.35:
            return self.rnd.choice(
                [str(self.rnd.randint(0, 50)), self.rnd.choice(self.vars)]
            )
        op = self.rnd.choice(["+", "-", "*"])
        return f"({self._num_expr(depth + 1)} {op} {self._num_expr(depth + 1)})"

    def _bool_expr(self, depth: int = 0) -> str:
        op = self.rnd.choice(["<", ">", "<=", ">=", "==", "!="])
        return f"{self._num_expr(depth + 1)} {op} {self._num_expr(depth + 1)}"


# ================================================================ 变异生成
class Mutator:
    """对种子用例做随机变异，构造可能触发边界错误的输入。"""

    KEYWORDS = ["let", "const", "if", "else", "while", "for", "return",
                "function", "number", "string", "boolean", "true", "false"]
    CHARS = list("(){}[];,+-*/=<>!&|.@\"'`%^~?:_0123456789abcxyz\n ")

    def __init__(self, seed: int = 0) -> None:
        self.rnd = random.Random(seed)

    def mutate(self, source: str) -> str:
        if not source:
            return source
        op = self.rnd.choice([
            "flip", "insert", "delete", "replace_kw", "truncate", "duplicate", "swap",
        ])
        text = list(source)
        if op == "flip":                      # 位翻转：改一个字符
            i = self.rnd.randrange(len(text))
            text[i] = self.rnd.choice(self.CHARS)
            return "".join(text)
        if op == "insert":                    # 插入一个字符
            i = self.rnd.randrange(len(text) + 1)
            text.insert(i, self.rnd.choice(self.CHARS))
            return "".join(text)
        if op == "delete":                    # 删除一段
            i = self.rnd.randrange(len(text))
            j = min(len(text), i + self.rnd.randint(1, 6))
            del text[i:j]
            return "".join(text)
        if op == "truncate":                  # 截断
            cut = self.rnd.randint(1, len(text))
            return source[:cut]
        if op == "duplicate":                 # 复制一行
            lines = source.splitlines()
            if lines:
                i = self.rnd.randrange(len(lines))
                lines.insert(i, lines[i])
            return "\n".join(lines)
        if op == "swap":                      # 交换两处片段
            if len(source) > 4:
                i = self.rnd.randrange(len(source) - 2)
                j = self.rnd.randrange(len(source) - 2)
                chars = list(source)
                chars[i], chars[j] = chars[j], chars[i]
                return "".join(chars)
            return source
        # replace_kw：把一个关键字换成另一个
        for keyword in self.KEYWORDS:
            if keyword in source:
                return source.replace(
                    keyword, self.rnd.choice(self.KEYWORDS), 1
                )
        return source


# ================================================================ 执行驱动
class FrontendRunner:
    """把用例输入整条编译器前端，捕获崩溃与超时。"""

    def run(self, case: FuzzCase, timeout_ms: float = 3000.0) -> FuzzResult:
        start = time.perf_counter()
        try:
            tokens, lex_errors = tokenize(case.source)
            program, parse_errors = parse(tokens)
            sema_errors, analyzer = analyze(program)
            irgen.generate(program, analyzer)
            elapsed = (time.perf_counter() - start) * 1000.0
            diagnostics = len(lex_errors) + len(parse_errors) + len(sema_errors)
            outcome = "diagnostics" if diagnostics else "ok"
            if elapsed > timeout_ms:
                return FuzzResult(case, "timeout", message=f"{elapsed:.0f} ms", elapsed_ms=elapsed)
            return FuzzResult(case, outcome, elapsed_ms=elapsed,
                              message=f"{diagnostics} 条诊断" if diagnostics else "")
        except Exception as exc:  # noqa: BLE001 —— 模糊测试就是要捕获一切异常
            elapsed = (time.perf_counter() - start) * 1000.0
            return FuzzResult(
                case, "crash",
                error_type=type(exc).__name__,
                message=str(exc) or exc.__class__.__name__,
                elapsed_ms=elapsed,
                detail=traceback.format_exc(),
            )


# ================================================================ 编排
class Fuzzer:
    def __init__(self, seed: int = 0, seeds: list[str] | None = None,
                 trace_path: str | None = None) -> None:
        self.seed = seed
        self.grammar = GrammarFuzzer(seed)
        self.mutator = Mutator(seed + 7919)
        self.runner = FrontendRunner()
        self.seed_corpus = list(seeds or [])
        # 每轮迭代前把「当前用例」落到该文件：一旦某次迭代卡住，
        # 就能从这里拿到导致卡死的输入用于复现。
        self.trace_path = trace_path

    def run(self, iterations: int = 200, max_seconds: float | None = None) -> FuzzReport:
        """运行模糊测试。

        ``max_seconds`` 是总时间预算：一旦超过就提前停止，即使某个变异输入让
        前端变慢，整个测试也不会无限期挂住。
        """
        report = FuzzReport()
        case_id = 0
        started = time.perf_counter()
        for _ in range(iterations):
            if max_seconds is not None and (time.perf_counter() - started) > max_seconds:
                break
            case_id += 1
            if self.seed_corpus and self.grammar.rnd.random() < 0.5:
                origin = self.grammar.rnd.choice(self.seed_corpus)
                source = self.mutator.mutate(origin)
                case = FuzzCase(case_id, source, "mutate", origin="种子")
            else:
                source = self.grammar.generate()
                case = FuzzCase(case_id, source, "grammar")
            report.cases.append(case)
            if self.trace_path:
                pathlib.Path(self.trace_path).write_text(
                    f"case #{case_id} ({case.strategy})\n{'=' * 40}\n{case.source}\n",
                    encoding="utf-8",
                )
            report.results.append(self.runner.run(case))
        return report