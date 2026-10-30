"""一键验证实验二：对所有样例执行「词法 -> 语法 -> 语义」完整前端分析。

运行::

    python build_sema.py

对 samples/sema_ok.ets 期望零语义错误；
对 samples/sema_errors.ets 期望报出多条语义错误并给出精确行列位置。
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from compiler.lexer import tokenize  # noqa: E402
from compiler.parser import parse  # noqa: E402
from compiler.sema import analyze  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent
SAMPLES = ROOT / "samples"


def main() -> int:
    targets = sorted(SAMPLES.glob("sema_*.ets"))
    if not targets:
        print("未找到 samples/sema_*.ets")
        return 1

    failures = 0
    print("=" * 72)
    print("Mini-ArkTS 编译器 · 实验二 语义分析验证")
    print("=" * 72)

    for path in targets:
        source = path.read_text(encoding="utf-8")
        expect_error = "errors" in path.name
        print(f"\n[{path.name}]  {'(预期报错样例)' if expect_error else ''}")

        tokens, lex_errors = tokenize(source, path.name)
        program, parse_errors = parse(tokens, path.name)
        sema_errors, analyzer = analyze(program, path.name)

        syntax_errors = lex_errors + parse_errors
        print(f"  Token 数   : {len(tokens)}")
        print(f"  类型定义   : {len(analyzer.registry.lookup('Base').members) if analyzer.registry.lookup('Base') else 0} 个成员(Base)")

        print(f"  词法错误   : {len(lex_errors)}")
        print(f"  语法错误   : {len(parse_errors)}")
        print(f"  语义错误   : {len(sema_errors)}")
        for err in sema_errors:
            print(f"    - {err}")

        if expect_error:
            if not sema_errors:
                failures += 1
                print("  !! 该样例应当报出语义错误，但未报出")
        else:
            if syntax_errors or sema_errors:
                failures += 1
                print("  !! 合法样例不应报错")

    print("\n" + "=" * 72)
    if failures:
        print(f"验证失败：{failures} 个样例不符合预期")
        return 1
    print("验证通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())