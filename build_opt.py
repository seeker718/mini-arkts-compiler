"""一键验证实验四：AOT 优化效果 + 模糊测试结果。

运行::

    python build_opt.py
    python build_opt.py --iterations 400 --seed 2024

第 1 部分对比 samples/optimize_*.ets 优化前后的 IR 与指令条数；
第 2 部分运行模糊测试器，统计用例数、诊断数与（去重后的）崩溃组。
"""

from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from compiler import irgen  # noqa: E402
from compiler.lexer import tokenize  # noqa: E402
from compiler.optimizer import diff_text, optimize  # noqa: E402
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


def main() -> int:
    parser = argparse.ArgumentParser(description="实验四：AOT 优化 + 模糊测试")
    parser.add_argument("--iterations", type=int, default=300, help="模糊测试迭代次数")
    parser.add_argument("--seed", type=int, default=2026, help="随机种子（可复现）")
    parser.add_argument("--max-seconds", type=float, default=60.0,
                        help="模糊测试总时间预算（秒），到点即停")
    args = parser.parse_args()

    OUT.mkdir(exist_ok=True)
    print("=" * 74)
    print("Mini-ArkTS 编译器 · 实验四 AOT 优化与模糊测试")
    print("=" * 74)

    # ---------------------------------------------------------- 1. 优化
    print("\n【第 1 部分】IR 优化效果")
    for path in sorted(SAMPLES.glob("optimize_*.ets")):
        before, errors = build_module(path)
        after, _ = build_module(path)
        stats = optimize(after)

        print(f"\n[{path.name}]")
        if errors:
            for err in errors:
                print(f"  !! {err}")
            continue
        print(f"  优化前指令 {stats['before']} 条 → 优化后 {stats['after']} 条 "
              f"（减少 {stats['before'] - stats['after']} 条）")
        print(f"  常量折叠 {stats['constant_folded']} 条，"
              f"分支化简 {stats['branch_simplified']} 处，"
              f"删除不可达块 {stats['block_removed']} 个，"
              f"删除无用指令 {stats['instruction_removed']} 条")
        print("  " + diff_text(before, after).replace("\n", "\n  "))
        (OUT / f"{path.stem}.opt.ir").write_text(after.to_text(), encoding="utf-8")
        (OUT / f"{path.stem}.before.ir").write_text(before.to_text(), encoding="utf-8")
        print(f"  优化前/后 IR -> out/{path.stem}.before.ir, out/{path.stem}.opt.ir")

    # ---------------------------------------------------------- 2. 模糊测试
    print("\n【第 2 部分】模糊测试")
    from compiler.fuzzer import Fuzzer  # 延迟导入，避免无谓开销

    seeds = [p.read_text(encoding="utf-8") for p in sorted(SAMPLES.glob("*.ets"))]
    fuzzer = Fuzzer(seed=args.seed, seeds=seeds,
                    trace_path=str(OUT / "fuzz_current.txt"))
    report = fuzzer.run(args.iterations, max_seconds=args.max_seconds)
    print(f"  种子语料 {len(seeds)} 份（来自 samples/*.ets），迭代 {args.iterations} 次，种子 {args.seed}")
    print()
    print(report.to_text())

    print("\n" + "=" * 74)
    crashes = report.stats()["crash"]
    if crashes:
        print(f"发现 {crashes} 例崩溃（已按指纹去重保存在报告中），需要进一步定位")
        return 1
    print("未发现崩溃：在该轮测试中前端保持了健壮性")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())