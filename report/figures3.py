"""生成实验三实验报告所需的示意图。

产物输出到 report/figures/：
    图3.1_IR生成流程图.png
    图3.2_IR结构示意.png
    图3.3_调度模拟流程.png
    图3.4_IR生成示例.png
    图3.5_调度结果对比.png
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

from compiler import dist_pass, distributed, irgen  # noqa: E402
from compiler.lexer import tokenize  # noqa: E402
from compiler.parser import parse  # noqa: E402
from compiler.sema import analyze  # noqa: E402

FIGDIR = ROOT / "report" / "figures"
SAMPLES = ROOT / "samples"

_IR_LOOP = (
    "遍历 AST，逐类节点生成 IR\n"
    "① 顶层 function → IRFunction；类/结构体方法 → IRFunction（名字如 Person.greet，带隐含 %this）\n"
    "② 语句 → 基本块 + br / jmp：if 生成 then/else/end 三块，while/for 生成 cond/body/update/end 四块\n"
    "③ 表达式 → 三地址码临时变量：%t1 = add %a, %b，子表达式自底向上归约\n"
    "④ 变量每次赋值产生新版本（SSA）：%x → %x.2 → %x.3\n"
    "⑤ 分支汇合处的变量版本用 φ 指令合并：%x.4 = phi [%x.2, then], [%x.3, else]\n"
    "⑥ 装饰器与 build() 声明式 UI 不参与计算型 IR，直接跳过"
)

_SCHED_LOOP = (
    "调度循环与模拟执行\n"
    "① 任务拆分：以函数为粒度切成任务单元，计算量 cost = 该函数的 IR 指令条数\n"
    "② 选择设备：按策略挑选目标节点（轮询 / 最短队列 / 数据本地化）\n"
    "③ 模拟执行：设备串行运行，耗时累加 cost / cpu_speed，跨设备调用再加网络延迟\n"
    "④ 统计指标：各设备负载、总工期 makespan = max(负载)、负载均衡度 balance"
)


def make_ir_flow(path: pathlib.Path) -> None:
    fig, ax = plt.subplots(figsize=(9.8, 10.5))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 118)
    ax.axis("off")

    _rounded(ax, 50, 112, 50, 9, "开始（实验二语义分析后的 AST）", FILL_START, 10)
    _rounded(ax, 50, 84, 92, 44, _IR_LOOP, FILL_LOOP, 7.6)
    _rounded(ax, 50, 48, 72, 12, "输出 IRModule：函数列表 + 基本块 + 三地址码指令（含 DeviceID）", FILL_IO, 9.5)
    _rounded(ax, 50, 30, 26, 9, "结束", FILL_START, 11)

    _arrow(ax, (50, 107.5), (50, 106.5))
    _arrow(ax, (50, 62.0), (50, 54.5))
    _arrow(ax, (50, 42.0), (50, 34.5))

    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


_IR_STRUCT = [
    "IRModule  mini_arkts_module",
    " ├─ global @P.x : number          (类字段 / 全局变量)",
    " ├─ IRFunction  square",
    " │   └─ IRBasicBlock entry",
    " │        ├─ %t1 = mul %p0_x, %p0_x",
    " │        └─ ret %t1",
    " ├─ IRFunction  classify",
    " │   ├─ IRBasicBlock entry",
    " │   │    ├─ %result = assign 1",
    " │   │    ├─ %t1 = gt %p0_value, 100",
    " │   │    └─ br %t1, if.then.1, if.else.2",
    " │   ├─ IRBasicBlock if.then.1",
    " │   │    ├─ %result.2 = assign 2",
    " │   │    └─ jmp if.end.3",
    " │   ├─ IRBasicBlock if.else.2",
    " │   │    ├─ %t2 = add %result, 0",
    " │   │    ├─ %result.3 = assign %t2",
    " │   │    └─ jmp if.end.3",
    " │   └─ IRBasicBlock if.end.3",
    " │        ├─ %result.4 = phi [%result.2, if.then.1], [%result.3, if.else.2]",
    " │        └─ ret %result.4",
    " └─ （每个 IRFunction / IRInstruction 都带 device 字段：0=本机，其余=远端设备）",
]


def make_ir_structure(path: pathlib.Path) -> None:
    _terminal_figure(_IR_STRUCT, path, fontsize=8, width_in=12.5)


def make_schedule_flow(path: pathlib.Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 8.5))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 118)
    ax.axis("off")

    _rounded(ax, 50, 112, 50, 9, "开始（IRModule + 设备拓扑）", FILL_START, 10)
    _rounded(ax, 50, 96, 84, 10, "任务拆分：按函数切成任务单元，cost = IR 指令条数", FILL_IO, 9)
    _rounded(ax, 50, 68, 92, 38, _SCHED_LOOP, FILL_LOOP, 8)
    _rounded(ax, 50, 36, 76, 12, "输出：任务分配表 + 各设备负载率 + makespan + 均衡度", FILL_IO, 9.5)
    _rounded(ax, 50, 18, 26, 9, "结束", FILL_START, 11)

    _arrow(ax, (50, 107.5), (50, 101.5))
    _arrow(ax, (50, 91.0), (50, 87.5))
    _arrow(ax, (50, 49.0), (50, 42.5))
    _arrow(ax, (50, 30.0), (50, 22.8))

    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def _build_module():
    source = (SAMPLES / "ir_demo.ets").read_text(encoding="utf-8")
    tokens, _ = tokenize(source, "ir_demo.ets")
    program, _ = parse(tokens, "ir_demo.ets")
    _, analyzer = analyze(program, "ir_demo.ets")
    module = irgen.generate(program, analyzer, "ir_demo.ets")
    dist_pass.mark_cross_device(module)
    return module


def make_ir_example(path: pathlib.Path) -> None:
    module = _build_module()
    lines = ["$ python main.py ir samples/ir_demo.ets", ""]
    text = module.to_text().splitlines()
    # 截取 classify 与 demo 两个函数作为示例
    start = next((i for i, l in enumerate(text) if l.startswith("func classify")), 0)
    lines.extend(text[start:start + 22])
    lines.append("...")
    lines.append(f"（共 {module.stats()['functions']} 个函数，"
                 f"{module.stats()['blocks']} 个基本块，{module.stats()['instructions']} 条指令）")
    _terminal_figure(lines, path, fontsize=8, width_in=12)


def make_schedule_chart(path: pathlib.Path) -> None:
    module = _build_module()
    tasks = distributed.tasks_from_module(module)
    devices = distributed.default_devices()
    results = distributed.compare_strategies(tasks, devices)
    names = ["round_robin", "least_loaded", "data_locality"]
    makespan = [results[n].makespan for n in names]
    balance = [results[n].balance for n in names]

    positions = list(range(len(names)))
    fig, ax = plt.subplots(figsize=(9.2, 5.2))
    ax.bar([p - 0.19 for p in positions], makespan, width=0.36,
           label="makespan 总工期（越小越好）", color="#58a6ff")
    ax.set_ylabel("makespan")
    ax.set_xticks(positions)
    ax.set_xticklabels(names, fontsize=10)
    ax.set_ylim(0, max(makespan) * 1.35 + 0.5)

    ax2 = ax.twinx()
    ax2.bar([p + 0.19 for p in positions], balance, width=0.36,
            label="balance 负载均衡度（越大越好）", color="#3fb950")
    ax2.set_ylabel("balance")
    ax2.set_ylim(0, 1.1)

    for p, value in zip(positions, makespan):
        ax.text(p - 0.19, value + 0.2, f"{value:.2f}", ha="center", fontsize=9, color="#1f4e8c")
    for p, value in zip(positions, balance):
        ax2.text(p + 0.19, value + 0.02, f"{value:.3f}", ha="center", fontsize=9, color="#1d6b32")

    handles1, labels1 = ax.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(handles1 + handles2, labels1 + labels2, loc="upper center",
              ncol=2, fontsize=9, frameon=False)
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    fig.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    FIGDIR.mkdir(parents=True, exist_ok=True)
    jobs = [
        (make_ir_flow, "图3.1_IR生成流程图.png"),
        (make_ir_structure, "图3.2_IR结构示意.png"),
        (make_schedule_flow, "图3.3_调度模拟流程.png"),
        (make_ir_example, "图3.4_IR生成示例.png"),
        (make_schedule_chart, "图3.5_调度结果对比.png"),
    ]
    for func, name in jobs:
        target = FIGDIR / name
        func(target)
        print(f"生成 {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())