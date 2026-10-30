"""分步诊断：定位编译器前端在 samples/optimize_demo.ets 上卡住的阶段。

每一步都立即 flush，因此即使整个命令被中断，也能从输出文件里
看到最后成功执行的阶段。
"""

from __future__ import annotations

import time


def stage(name: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {name}", flush=True)


source = open("samples/optimize_demo.ets", encoding="utf-8").read()
stage("0 start")

from compiler.lexer import tokenize  # noqa: E402

tokens, lex_errors = tokenize(source)
stage(f"1 lex done: {len(tokens)} tokens, {len(lex_errors)} errors")

from compiler.parser import parse  # noqa: E402

program, parse_errors = parse(tokens)
stage(f"2 parse done: {len(parse_errors)} errors, {len(program.body)} top-level nodes")

from compiler.sema import analyze  # noqa: E402

sema_errors, analyzer = analyze(program)
stage(f"3 sema done: {len(sema_errors)} errors")

from compiler import irgen  # noqa: E402

module = irgen.generate(program, analyzer)
stage(f"4 irgen done: {module.stats()}")

from compiler.optimizer import optimize  # noqa: E402

stats = optimize(module)
stage(f"5 optimize done: {stats}")

stage("ALL-DONE")