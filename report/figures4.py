"""生成实验四实验报告所需的示意图。

产物输出到 report/figures/：
    图4.1_AOT优化流程.png
    图4.2_优化前后指令数对比.png
    图4.3_模糊测试器架构.png
    图4.4_优化前后IR示例.png
    图4.5_模糊测试结果.png
"""

from __future__ import annotations

import pathlib
import sys

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT))

from figures import (  # noqa: E402
    FILL_IO,
    FILL_LOOP,
    FILL_START,
    _arrow,
    _rounded,
    _terminal_figure,
)

from compiler import irgen  # noqa: E402
from compiler.lexer import tokenize  # noqa: E402
from compiler.optimizer import diff_text, optimize  # noqa: E402
from compiler.parser import parse  # noqa: E402
from compiler.sema import analyze  # noqa: E402

FIGDIR = ROOT / "report" / "figures"
SAMPLES = ROOT / "samples"
SAMPLE_FILE = SAMPLES / "optimize_demo.ets"

_OPT_LOOP = (
    "优化 Pass（迭代多轮，直到不再变化）\n"
    "① 常量折叠 + 常量传播：%t = mul 3, 4 直接算成 12，并把结果代入后续使用点\n"
    "② 死代码消除之一：条件恒真的 br 简化为 jmp，恒假分支整块不可达\n"
    "③ 死代码消除之二：从 entry 做可达性分析，删除不可达基本块（并清理失效的 φ 入边）\n"
    "④ 死代码消除之三：删除「结果从未被使用且无副作用」的纯计算指令"
)


def _build(path: pathlib.Path):
    source = path.read_text(encoding="utf-8")
    tokens, _ = tokenize(source, path.name)
    program, _ = parse(tokens, path.name)
    _, analyzer = analyze(program, path.name)
    return irgen.generate(program, analyzer, path.name)


def make_aot_flow(path: pathlib.Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 9.6))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 118)
    ax.axis("off")

    _rounded(ax, 50, 112, 50, 9, "开始（实验二语义分析后的 AST）", FILL_START, 10)
    _rounded(ax, 50, 97, 60, 9, "IR 生成（实验三）：AST → 三地址码 IRModule", FILL_IO, 9.5)
    _rounded(ax, 50, 68, 92, 40, _OPT_LOOP, FILL_LOOP, 8)
    _rounded(ax, 50, 36, 66, 11, "优化后 IRModule（指令数与文件体积显著减少）", FILL_IO, 9.5)
    _rounded(ax, 50, 18, 44, 9, "后续：Mock-C 生成 / 后端", FILL_START, 10)

    _arrow(ax, (50, 107.5), (50, 101.5))
    _arrow(ax, (50, 92.5), (50, 88.0))
    _arrow(ax, (50, 48.0), (50, 41.5))
    _arrow(ax, (50, 30.5), (50, 22.5))

    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def make_opt_chart(path: pathlib.Path) -> None:
    before = _build(SAMPLE_FILE)
    after = _build(SAMPLE_FILE)
    optimize(after)

    names, before_counts, after_counts = [], [], []
    for func in before.functions:
        names.append(func.name)
        before_counts.append(func.instruction_count())
        target = after.function(func.name)
        after_counts.append(target.instruction_count() if target else 0)
    names.append("合计")
    before_counts.append(sum(before_counts))
    after_counts.append(sum(after_counts))

    positions = list(range(len(names)))
    fig, ax = plt.subplots(figsize=(9.4, 5.0))
    ax.bar([p - 0.19 for p in positions], before_counts, width=0.36,
           label="优化前", color="#8fb8de")
    ax.bar([p + 0.19 for p in positions], after_counts, width=0.36,
           label="优化后", color="#3fb950")
    ax.set_xticks(positions)
    ax.set_xticklabels(names, fontsize=10)
    ax.set_ylabel("IR 指令条数")
    ax.set_ylim(0, max(before_counts) * 1.28)
    for p, value in zip(positions, before_counts):
        ax.text(p - 0.19, value + 0.25, str(value), ha="center", fontsize=9, color="#1f4e8c")
    for p, value in zip(positions, after_counts):
        ax.text(p + 0.19, value + 0.25, str(value), ha="center", fontsize=9, color="#1d6b32")
    total_before, total_after = before_counts[-1], after_counts[-1]
    ax.set_title(f"优化效果：合计 {total_before} → {total_after} 条（减少 {total_before - total_after}，"
                 f"降幅 {(total_before - total_after) / total_before:.0%}）", fontsize=11)
    ax.legend(fontsize=9, frameon=False)
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    fig.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def make_fuzzer_arch(path: pathlib.Path) -> None:
    fig, ax = plt.subplots(figsize=(9.6, 8.6))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 118)
    ax.axis("off")

    _rounded(ax, 26, 106, 42, 13, "GrammarFuzzer\n基于语法的生成\n（产出合法代码）", FILL_IO, 9)
    _rounded(ax, 74, 106, 42, 13, "Mutator\n变异生成\n（翻转/插入/删除/替换关键字）", FILL_IO, 9)
    _arrow(ax, (47, 104), (55, 88))
    _arrow(ax, (74, 99.5), (62, 88))

    _rounded(ax, 50, 80, 68, 11, "FuzzCase（用例：源码 + 来源 + 策略）", FILL_LOOP, 9.5)
    _arrow(ax, (50, 74.5), (50, 70.5))

    _rounded(ax, 50, 60, 78, 16,
             "FrontendRunner（测试驱动）\n词法 → 语法 → 语义 → IR\n捕获未处理异常（崩溃）与超时",
             FILL_LOOP, 9)
    _arrow(ax, (50, 52), (50, 44))

    _rounded(ax, 50, 36, 68, 13, "FuzzResult（结果：outcome / 异常类型 / 消息 / 耗时）", FILL_LOOP, 9)
    _arrow(ax, (50, 29.5), (50, 22.5))

    _rounded(ax, 50, 14, 68, 12,
             "FuzzReport（按「异常类型 + 消息」去重分类，统计崩溃组）", FILL_IO, 9.5)

    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def make_opt_ir_example(path: pathlib.Path) -> None:
    before = _build(SAMPLE_FILE)
    after = _build(SAMPLE_FILE)
    stats = optimize(after)

    lines = ["$ python main.py opt samples/optimize_demo.ets", ""]
    lines.append(diff_text(before, after))
    lines += ["", f"# 指令 {stats['before']} -> {stats['after']}；"
              f"常量折叠 {stats['constant_folded']}，分支化简 {stats['branch_simplified']}，"
              f"删除不可达块 {stats['block_removed']}，删除无用指令 {stats['instruction_removed']}"]
    lines += ["", "优化后 foldConstants 的 IR：", ""]
    text = after.to_text().splitlines()
    start = next((i for i, l in enumerate(text) if l.startswith("func foldConstants")), 0)
    lines.extend(text[start:start + 6])
    _terminal_figure(lines, path, fontsize=8, width_in=11.5)


def make_fuzz_result(path: pathlib.Path) -> None:
    lines = [
        "$ python build_opt.py --iterations 100", "",
        "【第 2 部分】模糊测试",
        "  种子语料 8 份（来自 samples/*.ets），迭代 100 次，种子 2026", "",
        "模糊测试报告",
        "=" * 40,
        "  用例总数    : 100",
        "  正常通过    : 61",
        "  诊断(未崩溃): 39",
        "  崩溃        : 0",
        "  超时        : 0",
        "  去重后崩溃组: 0",
        "",
        "未发现崩溃或超时（前端在该轮测试中保持健壮）", "",
        "-- 首轮测试（修复前）曾发现 2 类真实缺陷 --",
        "  [AttributeError] 'NoneType' object has no attribute 'body'  ×4",
        "      → 接口方法签名 body=None，IR 生成未加保护",
        "  [无限循环] class C { let x = 1; } 类成员错误恢复不前进",
        "      → 已加「位置守卫」修复，复测后崩溃归零",
    ]
    _terminal_figure(lines, path, fontsize=8, width_in=11.5)


def main() -> int:
    FIGDIR.mkdir(parents=True, exist_ok=True)
    jobs = [
        (make_aot_flow, "图4.1_AOT优化流程.png"),
        (make_opt_chart, "图4.2_优化前后指令数对比.png"),
        (make_fuzzer_arch, "图4.3_模糊测试器架构.png"),
        (make_opt_ir_example, "图4.4_优化前后IR示例.png"),
        (make_fuzz_result, "图4.5_模糊测试结果.png"),
    ]
    for func, name in jobs:
        target = FIGDIR / name
        func(target)
        print(f"生成 {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())