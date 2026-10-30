"""Mini-ArkTS 编译器命令行入口（实验一）。

用法::

    python main.py lex   samples/counter.ets
    python main.py parse samples/counter.ets --json out/counter.json --html out/counter.html
    python main.py ast   samples/counter.ets          # 终端打印 S-表达式
"""

from __future__ import annotations

import argparse
import pathlib
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from compiler.ast_json import to_json, to_sexpr  # noqa: E402
from compiler.lexer import tokenize  # noqa: E402
from compiler.parser import parse  # noqa: E402
from compiler import (  # noqa: E402
    cgen,
    dist_pass,
    distributed,
    fuzzer,
    irgen,
    optimizer,
)
from compiler.sema import analyze  # noqa: E402
from compiler.visualize import write_html  # noqa: E402


def _read_source(path: str) -> str:
    return pathlib.Path(path).read_text(encoding="utf-8")


def _report_errors(errors, label: str) -> None:
    if not errors:
        print(f"  {label}: 无错误")
        return
    print(f"  {label}: {len(errors)} 个错误")
    for err in errors:
        print(f"    {err}")


def cmd_lex(args) -> int:
    source = _read_source(args.file)
    tokens, errors = tokenize(source, args.file)
    for tok in tokens:
        print(f"{tok.line:>4}:{tok.column:<4} {tok.type.name:<16} {tok.value!r}")
    _report_errors(errors, "词法")
    return 1 if errors else 0


def cmd_ast(args) -> int:
    source = _read_source(args.file)
    tokens, lex_errors = tokenize(source, args.file)
    program, parse_errors = parse(tokens, args.file)
    print(to_sexpr(program))
    _report_errors(lex_errors, "词法")
    _report_errors(parse_errors, "语法")
    return 1 if (lex_errors or parse_errors) else 0


def cmd_parse(args) -> int:
    source = _read_source(args.file)
    tokens, lex_errors = tokenize(source, args.file)
    program, parse_errors = parse(tokens, args.file)
    errors = lex_errors + parse_errors

    stem = pathlib.Path(args.file).stem
    if args.json:
        out_json = pathlib.Path(args.json)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(to_json(program), encoding="utf-8")
        print(f"AST JSON -> {out_json}")
    if args.html:
        out_html = write_html(program, args.html, title=f"AST: {stem}", source=source)
        print(f"AST 可视化 -> {out_html}")

    print(f"Token 数: {len(tokens)}")
    _report_errors(lex_errors, "词法")
    _report_errors(parse_errors, "语法")
    return 1 if errors else 0


def cmd_sema(args) -> int:
    """完整前端：词法 + 语法 + 语义分析（实验二）。"""
    source = _read_source(args.file)
    tokens, lex_errors = tokenize(source, args.file)
    program, parse_errors = parse(tokens, args.file)
    sema_errors, _ = analyze(program, args.file)
    errors = lex_errors + parse_errors + sema_errors

    print(f"Token 数: {len(tokens)}")
    _report_errors(lex_errors, "词法")
    _report_errors(parse_errors, "语法")
    _report_errors(sema_errors, "语义")
    return 1 if errors else 0


def _build_ir(file: str):
    source = _read_source(file)
    tokens, lex_errors = tokenize(source, file)
    program, parse_errors = parse(tokens, file)
    sema_errors, analyzer = analyze(program, file)
    module = irgen.generate(program, analyzer, file)
    return module, lex_errors + parse_errors + sema_errors


def cmd_ir(args) -> int:
    """打印 AST -> IR 的转换结果（实验三）。"""
    module, errors = _build_ir(args.file)
    print(module.to_text())
    stats = module.stats()
    print(f"# 函数 {stats['functions']}，基本块 {stats['blocks']}，"
          f"IR 指令 {stats['instructions']}")
    if args.out:
        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(module.to_text(), encoding="utf-8")
        print(f"IR 文本 -> {out}")
    _report_errors(errors, "前端")
    return 1 if errors else 0


def cmd_cgen(args) -> int:
    """生成 Mock-C 代码（含分布式 RPC 桩）。"""
    module, errors = _build_ir(args.file)
    dist_pass.mark_cross_device(module)
    c_source = cgen.generate_c(module, entry=args.entry)
    c_source += "\n" + dist_pass.generate_rpc_stubs(module) + "\n"
    out = pathlib.Path(args.out) if args.out else pathlib.Path(pathlib.Path(args.file).stem + ".c")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(c_source, encoding="utf-8")
    print(f"Mock-C 代码 -> {out}（{len(c_source.splitlines())} 行）")
    print(dist_pass.cross_device_report(module))
    _report_errors(errors, "前端")
    return 1 if errors else 0


def cmd_dist(args) -> int:
    """分布式调度模拟：对比三种调度策略。"""
    module, errors = _build_ir(args.file)
    dist_pass.mark_cross_device(module)
    tasks = distributed.tasks_from_module(module)
    devices = distributed.default_devices()
    print(f"设备节点 {len(devices)} 个，任务单元 {len(tasks)} 个")
    print(dist_pass.cross_device_report(module))
    for strategy in ("round_robin", "least_loaded", "data_locality"):
        result = distributed.schedule(tasks, devices, strategy)
        print()
        print(result.report())
    _report_errors(errors, "前端")
    return 1 if errors else 0


def cmd_opt(args) -> int:
    """IR 级 AOT 优化（常量折叠 + 死代码消除）并对比优化前后。"""
    before, errors = _build_ir(args.file)
    after, _ = _build_ir(args.file)
    stats = optimizer.optimize(after)
    print(optimizer.diff_text(before, after))
    print()
    print(f"# 指令 {stats['before']} -> {stats['after']}；"
          f"常量折叠 {stats['constant_folded']}，分支化简 {stats['branch_simplified']}，"
          f"删除不可达块 {stats['block_removed']}，删除无用指令 {stats['instruction_removed']}")
    if args.ir:
        print()
        print(after.to_text())
    _report_errors(errors, "前端")
    return 1 if errors else 0


def cmd_fuzz(args) -> int:
    """运行编译器前端模糊测试。"""
    corpus_dir = pathlib.Path(args.corpus)
    seeds = []
    if corpus_dir.is_dir():
        seeds = [p.read_text(encoding="utf-8") for p in sorted(corpus_dir.glob("*.ets"))]
    engine = fuzzer.Fuzzer(seed=args.seed, seeds=seeds)
    report = engine.run(args.iterations, max_seconds=args.max_seconds)
    print(f"种子语料 {len(seeds)} 份，迭代 {args.iterations} 次，随机种子 {args.seed}")
    print()
    print(report.to_text())
    return 1 if report.stats()["crash"] else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="main.py", description="Mini-ArkTS 编译器（实验一）")
    sub = parser.add_subparsers(dest="command", required=True)

    p_lex = sub.add_parser("lex", help="只做词法分析，打印 Token 流")
    p_lex.add_argument("file")
    p_lex.set_defaults(func=cmd_lex)

    p_ast = sub.add_parser("ast", help="打印 AST 的 S-表达式")
    p_ast.add_argument("file")
    p_ast.set_defaults(func=cmd_ast)

    p_parse = sub.add_parser("parse", help="完整前端：词法 + 语法 + 导出")
    p_parse.add_argument("file")
    p_parse.add_argument("--json", help="导出 AST JSON 的路径")
    p_parse.add_argument("--html", help="导出 AST 可视化 HTML 的路径")
    p_parse.set_defaults(func=cmd_parse)

    p_sema = sub.add_parser("sema", help="词法 + 语法 + 语义分析")
    p_sema.add_argument("file")
    p_sema.set_defaults(func=cmd_sema)

    p_ir = sub.add_parser("ir", help="生成三地址码 IR")
    p_ir.add_argument("file")
    p_ir.add_argument("--out", help="IR 文本输出路径")
    p_ir.set_defaults(func=cmd_ir)

    p_cgen = sub.add_parser("cgen", help="生成 Mock-C 代码（含 RPC 桩）")
    p_cgen.add_argument("file")
    p_cgen.add_argument("--out", help="C 代码输出路径")
    p_cgen.add_argument("--entry", default="demo", help="C 的 main 入口函数名")
    p_cgen.set_defaults(func=cmd_cgen)

    p_dist = sub.add_parser("dist", help="分布式调度模拟")
    p_dist.add_argument("file")
    p_dist.set_defaults(func=cmd_dist)

    p_opt = sub.add_parser("opt", help="IR 级 AOT 优化并对比优化前后")
    p_opt.add_argument("file")
    p_opt.add_argument("--ir", action="store_true", help="额外打印优化后的完整 IR")
    p_opt.set_defaults(func=cmd_opt)

    p_fuzz = sub.add_parser("fuzz", help="编译器前端模糊测试")
    p_fuzz.add_argument("--iterations", type=int, default=300)
    p_fuzz.add_argument("--seed", type=int, default=2026)
    p_fuzz.add_argument("--corpus", default="samples", help="种子语料目录")
    p_fuzz.add_argument("--max-seconds", type=float, default=60.0, help="总时间预算（秒）")
    p_fuzz.set_defaults(func=cmd_fuzz)

    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())