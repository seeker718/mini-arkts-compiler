"""生成实验一实验报告所需的示意图（matplotlib，中文字体）。

产物输出到 report/figures/：
    图1.1_词法分析流程图.png
    图1.2_语法分析流程图.png
    图1.3_hello的AST.png
    图1.4_hello的词法输出.png
"""

from __future__ import annotations

import pathlib
import sys
from dataclasses import fields

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compiler.ast_nodes import Node  # noqa: E402
from compiler.lexer import tokenize  # noqa: E402
from compiler.parser import parse  # noqa: E402

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

FIGDIR = ROOT / "report" / "figures"
SAMPLES = ROOT / "samples"

EDGE = "#33506e"
FILL_PROC = "#e9f2ff"
FILL_LOOP = "#fff6d9"
FILL_START = "#d8ecff"
FILL_IO = "#e2f5e6"
MONO = ["Consolas", "Microsoft YaHei", "DejaVu Sans Mono"]

_LEX_LOOP = (
    "循环：直到源码末尾\n"
    "① 跳过空白与注释（// 行注释、/* 块注释 */）\n"
    "② 按最长匹配识别下一个词素：数字 / 字符串 / 模板串 / 标识符 / 关键字 / 运算符\n"
    "③ 生成 Token，记录 line / col，推进扫描游标\n"
    "④ 识别失败（非法字符、未闭合字符串或注释）→ 记录诊断并跳过，保证扫描继续"
)

_PARSE_LOOP = (
    "循环：直到 Token 流末尾\n"
    "① 递归下降解析一条语句，按 12 级优先级自底向上归约\n"
    "   赋值 → 条件 → 逻辑 → 位 → 相等 → 关系 → 移位 → 加减 → 乘除 → 一元 → 后缀 → 原子\n"
    "② 解析成功 → 构造对应的 AST 节点\n"
    "③ 解析失败 → 记录诊断，按「同步集」跳到下一条语句起点后继续"
)


def _rounded(ax, cx, cy, w, h, text, fill=FILL_PROC, fontsize=10):
    patch = FancyBboxPatch(
        (cx - w / 2, cy - h / 2), w, h,
        boxstyle="round,pad=0.2,rounding_size=1.5",
        linewidth=1.3, edgecolor=EDGE, facecolor=fill,
    )
    ax.add_patch(patch)
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fontsize, linespacing=1.7)


def _arrow(ax, p1, p2):
    ax.add_patch(
        FancyArrowPatch(p1, p2, arrowstyle="-|>", mutation_scale=13,
                        linewidth=1.3, color=EDGE, shrinkA=0, shrinkB=0)
    )


def _flow_figure():
    fig, ax = plt.subplots(figsize=(9.6, 11))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 118)
    ax.axis("off")
    return fig, ax


def make_lexer_flow(path: pathlib.Path) -> None:
    fig, ax = _flow_figure()
    _rounded(ax, 50, 108, 24, 9, "开始", FILL_START, 11)
    _rounded(ax, 50, 93, 62, 10, "初始化扫描游标：pos = 0, line = 1, col = 1")
    _rounded(ax, 50, 69, 88, 36, _LEX_LOOP, FILL_LOOP, 8.5)
    _rounded(ax, 50, 44, 40, 10, "追加 EOF 结束符", FILL_IO)
    _rounded(ax, 50, 30, 64, 10, "输出 Token 序列与错误集合", FILL_IO)
    _rounded(ax, 50, 16, 24, 9, "结束", FILL_START, 11)

    _arrow(ax, (50, 103.5), (50, 98.2))
    _arrow(ax, (50, 88.0), (50, 87.2))
    _arrow(ax, (50, 51.0), (50, 49.2))
    _arrow(ax, (50, 39.0), (50, 35.2))
    _arrow(ax, (50, 25.0), (50, 20.7))

    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def make_parser_flow(path: pathlib.Path) -> None:
    fig, ax = _flow_figure()
    _rounded(ax, 50, 108, 24, 9, "开始", FILL_START, 11)
    _rounded(ax, 50, 93, 62, 10, "读入 Token 序列，创建 Parser 实例")
    _rounded(ax, 50, 68, 90, 38, _PARSE_LOOP, FILL_LOOP, 8)
    _rounded(ax, 50, 38, 70, 11, "输出 AST：S-表达式 / JSON / HTML 可视化", FILL_IO)
    _rounded(ax, 50, 20, 24, 9, "结束", FILL_START, 11)

    _arrow(ax, (50, 103.5), (50, 98.2))
    _arrow(ax, (50, 88.0), (50, 87.2))
    _arrow(ax, (50, 49.0), (50, 43.8))
    _arrow(ax, (50, 32.5), (50, 24.7))

    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


# ------------------------------------------------------------------ AST 缩进树
_KEY_FIELDS = ("kind", "name", "operator", "value", "literal_type", "extends")


def _short_attrs(node: Node) -> str:
    parts = []
    seen = set()
    for key in _KEY_FIELDS:
        if key in seen or not hasattr(node, key):
            continue
        seen.add(key)
        value = getattr(node, key)
        if value in (None, "", [], False):
            continue
        parts.append(f"{key}={value!r}" if isinstance(value, str) else f"{key}={value}")
    return ("   " + " ".join(parts)) if parts else ""


def _node_children(node: Node) -> list:
    kids = []
    for f in fields(node):
        value = getattr(node, f.name)
        if isinstance(value, Node):
            kids.append(value)
        elif isinstance(value, list):
            kids.extend(v for v in value if isinstance(v, Node))
    return kids


def _tree_lines(node: Node, prefix: str = "", is_last: bool = True,
                is_root: bool = True, out: list | None = None) -> list:
    if out is None:
        out = []
    connector = "" if is_root else ("└─ " if is_last else "├─ ")
    out.append(f"{prefix}{connector}{type(node).__name__}{_short_attrs(node)}")
    child_prefix = prefix + ("" if is_root else ("   " if is_last else "│  "))
    kids = _node_children(node)
    for i, child in enumerate(kids):
        _tree_lines(child, child_prefix, i == len(kids) - 1, False, out)
    return out


def _terminal_figure(lines: list[str], path: pathlib.Path, fontsize: float = 7.5,
                     width_in: float = 10.5) -> None:
    line_h = fontsize * 1.62 / 72.0
    height_in = max(2.0, len(lines) * line_h + 0.5)
    fig, ax = plt.subplots(figsize=(width_in, height_in))
    fig.subplots_adjust(0, 0, 1, 1)
    ax.axis("off")
    ax.add_patch(Rectangle((0, 0), 1, 1, transform=ax.transAxes,
                           facecolor="#10151d", edgecolor="#2a3646", linewidth=1.2))
    ax.text(0.012, 0.985, "\n".join(lines), transform=ax.transAxes, ha="left", va="top",
            fontsize=fontsize, color="#c9f7d0", family=MONO, linespacing=1.62)
    fig.savefig(path, dpi=200)
    plt.close(fig)


def make_ast_figure(path: pathlib.Path) -> None:
    source = (SAMPLES / "hello.ets").read_text(encoding="utf-8")
    tokens, _ = tokenize(source, "hello.ets")
    program, _ = parse(tokens, "hello.ets")
    lines = ["$ python main.py ast samples/hello.ets", ""]
    lines += _tree_lines(program)
    lines += ["", f"（共 {len(lines) - 3} 行节点；完整可交互树见 out/hello.html）"]
    _terminal_figure(lines, path)


def make_token_figure(path: pathlib.Path) -> None:
    source = (SAMPLES / "hello.ets").read_text(encoding="utf-8")
    tokens, errors = tokenize(source, "hello.ets")
    lines = ["$ python main.py lex samples/hello.ets", ""]
    lines.append(f"{'行:列':>8}  {'Token 类型':<16} 词素")
    lines.append("-" * 46)
    for tok in tokens[:22]:
        lines.append(f"{tok.line:>4}:{tok.column:<3}  {tok.type.name:<16} {tok.value!r}")
    lines.append(f"{'...':>8}  （共 {len(tokens)} 个 Token，{len(errors)} 个词法错误）")
    _terminal_figure(lines, path, fontsize=8)


def main() -> int:
    FIGDIR.mkdir(parents=True, exist_ok=True)
    jobs = [
        (make_lexer_flow, "图1.1_词法分析流程图.png"),
        (make_parser_flow, "图1.2_语法分析流程图.png"),
        (make_ast_figure, "图1.3_hello的AST.png"),
        (make_token_figure, "图1.4_hello的词法输出.png"),
    ]
    for func, name in jobs:
        target = FIGDIR / name
        func(target)
        print(f"生成 {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())