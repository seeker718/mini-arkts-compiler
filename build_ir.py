"""一键验证实验三：AST -> IR -> Mock-C -> 分布式调度模拟。

运行::

    python build_ir.py

流程：
    1. 对 samples/ir_*.ets 依次执行 词法 -> 语法 -> 语义 -> IR 生成；
    2. 把 IR 文本写入 out/<样例>.ir；
    3. 跑分布式 Pass（标记可跨设备函数），生成 RPC 桩；
    4. 生成 Mock-C 代码到 out/<样例>.c；
    5. 若本机有 gcc / clang，则编译并运行，验证计算结果；
    6. 用三种调度策略模拟任务分配，打印对比数据。
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from compiler import cgen, dist_pass, distributed, irgen  # noqa: E402
from compiler.lexer import tokenize  # noqa: E402
from compiler.parser import parse  # noqa: E402
from compiler.sema import analyze  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent
SAMPLES = ROOT / "samples"
OUT = ROOT / "out"


def build_module(path: pathlib.Path):
    source = path.read_text(encoding="utf-8")
    tokens, lex_errors = tokenize(source, path.name)
    program, parse_errors = parse(tokens, path.name)
    sema_errors, analyzer = analyze(program, path.name)
    module = irgen.generate(program, analyzer, path.name)
    return module, lex_errors + parse_errors + sema_errors


def try_compile_and_run(c_path: pathlib.Path, exe_path: pathlib.Path) -> str:
    cc = shutil.which("gcc") or shutil.which("clang")
    if cc is None:
        return "未找到 gcc / clang，跳过编译运行"
    try:
        build = subprocess.run(
            [cc, str(c_path), "-o", str(exe_path), "-lm"],
            capture_output=True, text=True, timeout=60,
        )
        if build.returncode != 0:
            return f"编译失败：\n{build.stderr.strip()[:400]}"
        run = subprocess.run([str(exe_path)], capture_output=True, text=True, timeout=30)
        return f"编译成功，运行输出：{(run.stdout.strip() or run.stderr.strip())[:200]}"
    except Exception as exc:  # noqa: BLE001
        return f"编译/运行异常：{exc}"


def main() -> int:
    OUT.mkdir(exist_ok=True)
    targets = sorted(SAMPLES.glob("ir_*.ets"))
    if not targets:
        print("未找到 samples/ir_*.ets")
        return 1

    print("=" * 74)
    print("Mini-ArkTS 编译器 · 实验三 IR 生成与分布式调度模拟")
    print("=" * 74)

    for path in targets:
        module, errors = build_module(path)
        print(f"\n[{path.name}]")
        if errors:
            for err in errors:
                print(f"  !! {err}")
            continue

        stats = module.stats()
        print(f"  函数 {stats['functions']} 个，基本块 {stats['blocks']} 个，"
              f"IR 指令 {stats['instructions']} 条")

        (OUT / f"{path.stem}.ir").write_text(module.to_text(), encoding="utf-8")
        print(f"  IR 文本 -> out/{path.stem}.ir")

        # 分布式 Pass
        dist_pass.mark_cross_device(module)
        print("  " + dist_pass.cross_device_report(module).replace("\n", "\n  "))

        # Mock-C 代码：主代码 + RPC 桩
        c_source = cgen.generate_c(module) + "\n" + dist_pass.generate_rpc_stubs(module) + "\n"
        c_path = OUT / f"{path.stem}.c"
        c_path.write_text(c_source, encoding="utf-8")
        print(f"  Mock-C 代码 -> out/{path.stem}.c  ({len(c_source.splitlines())} 行)")

        print("  " + try_compile_and_run(c_path, OUT / f"{path.stem}.exe"))

        # 分布式调度模拟
        tasks = distributed.tasks_from_module(module)
        devices = distributed.default_devices()
        print(f"\n  ---- 分布式调度模拟（{len(devices)} 个设备节点，{len(tasks)} 个任务单元）----")
        results = distributed.compare_strategies(tasks, devices)
        for name, result in results.items():
            print(f"  [{name}] makespan={result.makespan:.2f}  "
                  f"balance={result.balance:.3f}  负载={ {k: round(v, 2) for k, v in result.device_load.items()} }")

    print("\n" + "=" * 74)
    print(f"产物已输出到 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())