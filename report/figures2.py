"""生成实验二实验报告所需的示意图。

产物输出到 report/figures/：
    图2.1_语义分析流程图.png
    图2.2_作用域链.png
    图2.3_类型检查规则.png
    图2.4_语义错误输出.png
"""

from __future__ import annotations

import pathlib
import sys

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT))

from figures import (  # noqa: E402
    EDGE,
    FILL_IO,
    FILL_LOOP,
    FILL_START,
    _arrow,
    _rounded,
    _terminal_figure,
)

FIGDIR = ROOT / "report" / "figures"

_PASS1 = (
    "第一遍：符号表构建\n"
    "① 登记 class / struct / interface 的空壳类型（为互相引用做准备）\n"
    "② 填充成员：字段类型、方法签名、可见性（public / private / protected）\n"
    "③ 声明函数与全局变量，登记到全局作用域\n"
    "④ 检查 implements 的接口成员是否在类中被实现"
)

_PASS2 = (
    "第二遍：语义检查（沿作用域链自顶向下遍历 AST）\n"
    "① 进入类作用域 → 进入方法作用域 → 进入块作用域，逐条检查语句与表达式\n"
    "② 类型检查：赋值、二元运算、函数传参、返回值都要求类型兼容\n"
    "③ 类型推断：let x = 10 ⇒ x 推断为 number\n"
    "④ 可见性检查：private / protected 成员是否可在当前位置访问\n"
    "⑤ 装饰器语义校验：@State 等状态装饰器是否位于带 @Entry 的组件内"
)


def make_sema_flow(path: pathlib.Path) -> None:
    fig, ax = plt.subplots(figsize=(9.6, 11))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 118)
    ax.axis("off")

    _rounded(ax, 50, 112, 46, 9, "开始（输入实验一产出的 AST）", FILL_START, 10)
    _rounded(ax, 50, 96, 90, 17, _PASS1, FILL_LOOP, 8.5)
    _rounded(ax, 50, 71, 90, 25, _PASS2, FILL_LOOP, 8)
    _rounded(ax, 50, 46, 74, 11, "输出：带类型的 AST + 语义错误列表（类型/位置/描述）", FILL_IO)
    _rounded(ax, 50, 30, 24, 9, "结束", FILL_START, 11)

    _arrow(ax, (50, 107.5), (50, 104.5))
    _arrow(ax, (50, 87.5), (50, 83.5))
    _arrow(ax, (50, 58.5), (50, 51.5))
    _arrow(ax, (50, 40.5), (50, 34.5))

    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def make_scope_chain(path: pathlib.Path) -> None:
    fig, ax = plt.subplots(figsize=(9.2, 7.2))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")

    layers = [
        # (x0, y0, x1, y1, 标题, 符号列表)
        (3, 6, 97, 94, "全局作用域 global", ["函数 fib", "类 Person", "struct Counter"]),
        (10, 14, 90, 82, "组件作用域 Counter（struct）", ["@State count: number", "@Prop step: number", "方法 increment"]),
        (17, 22, 83, 66, "方法作用域 increment(step)", ["参数 step: number", "局部变量（无）"]),
        (24, 30, 76, 50, "块作用域（for / if 的体）", ["let t: number"]),
    ]
    colors = ["#f2f6fc", "#e8f0fe", "#e2f5e6", "#fff6d9"]
    for (x0, y0, x1, y1, title, symbols), color in zip(layers, colors):
        ax.add_patch(
            FancyBboxPatch((x0, y0), x1 - x0, y1 - y0,
                           boxstyle="round,pad=0.2,rounding_size=1.4",
                           linewidth=1.3, edgecolor=EDGE, facecolor=color)
        )
        ax.text(x0 + 1.6, y1 - 7, title, fontsize=10, fontweight="bold", color="#1f3a5f")
        for i, item in enumerate(symbols):
            ax.text(x0 + 3.4, y1 - 13 - i * 5.0, "· " + item, fontsize=8.5, color="#3c4a5c")

    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


_TYPE_RULES = [
    "$ 类型兼容性判定  is_assignable(src, dst)",
    "",
    "  number   -> number            OK   同类型",
    "  string   -> string            OK   同类型",
    "  number   -> string            X    去动态化：禁止隐式转换",
    "  string   -> number            X    去动态化：禁止隐式转换",
    "  number   -> any               OK   any 视为兼容",
    "  Circle   -> Shape             OK   子类型（class implements interface）",
    "  Base     -> Derived           X    父类不能赋给子类",
    "  number[] -> number[]          OK   数组元素递归判定",
    "  (number)=>number -> 同签名    OK   参数与返回值分别判定",
    "",
    "$ 运算与语句规则",
    "",
    "  number + number  =>  number        number + string  =>  报错",
    "  string + string  =>  string        if / while 条件  =>  必须 boolean",
    "  函数调用         =>  参数个数与类型须与签名一致",
    "  return           =>  须可赋值给声明的返回类型",
]


def make_type_rules(path: pathlib.Path) -> None:
    _terminal_figure(_TYPE_RULES, path, fontsize=8, width_in=11)


def make_sema_output(path: pathlib.Path) -> None:
    from compiler.lexer import tokenize
    from compiler.parser import parse
    from compiler.sema import analyze

    source = (ROOT / "samples" / "sema_errors.ets").read_text(encoding="utf-8")
    tokens, _ = tokenize(source, "sema_errors.ets")
    program, _ = parse(tokens, "sema_errors.ets")
    errors, _ = analyze(program, "sema_errors.ets")

    lines = ["$ python main.py sema samples/sema_errors.ets", ""]
    for err in errors:
        lines.append(f"  {err}")
    lines += ["", f"  共 {len(errors)} 条语义错误（每条都带 行:列 位置）"]
    _terminal_figure(lines, path, fontsize=7.5, width_in=11.5)


def main() -> int:
    FIGDIR.mkdir(parents=True, exist_ok=True)
    jobs = [
        (make_sema_flow, "图2.1_语义分析流程图.png"),
        (make_scope_chain, "图2.2_作用域链.png"),
        (make_type_rules, "图2.3_类型检查规则.png"),
        (make_sema_output, "图2.4_语义错误输出.png"),
    ]
    for func, name in jobs:
        target = FIGDIR / name
        func(target)
        print(f"生成 {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())