"""一键验证实验一：跑通所有样例，导出 JSON / HTML 产物。

运行::

    python build.py

它会：
1. 遍历 samples/*.ets；
2. 对每个样例执行「词法 -> 语法 -> AST」；
3. 把产物写到 out/<样例名>.json 与 out/<样例名>.html；
4. 打印 Token 数、AST 节点数、错误列表，并对 bad_syntax.ets 校验「确实报错」。
"""

from __future__ import annotations

import pathlib
import sys
from dataclasses import fields

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from compiler.ast_json import node_to_dict, to_json  # noqa: E402
from compiler.lexer import tokenize  # noqa: E402
from compiler.parser import parse  # noqa: E402
from compiler.visualize import write_html  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent
SAMPLES = ROOT / "samples"
OUT = ROOT / "out"


def count_nodes(node) -> int:
    total = 1
    for f in fields(node):
        value = getattr(node, f.name)
        if isinstance(value, list):
            total += sum(count_nodes(v) for v in value if hasattr(v, "__dataclass_fields__"))
        elif hasattr(value, "__dataclass_fields__"):
            total += count_nodes(value)
    return total


def main() -> int:
    OUT.mkdir(exist_ok=True)
    failures = 0
    print("=" * 70)
    print("Mini-ArkTS 编译器 · 实验一 一键验证")
    print("=" * 70)

    for src_path in sorted(SAMPLES.glob("*.ets")):
        source = src_path.read_text(encoding="utf-8")
        expect_error = "bad_" in src_path.name
        print(f"\n[{src_path.name}]  {'(预期报错样例)' if expect_error else ''}")

        tokens, lex_errors = tokenize(source, src_path.name)
        program, parse_errors = parse(tokens, src_path.name)
        errors = lex_errors + parse_errors
        nodes = count_nodes(program)

        print(f"  Token 数 : {len(tokens)}")
        print(f"  AST 节点 : {nodes}")
        print(f"  错误数   : {len(errors)}")
        for err in errors:
            print(f"    - {err}")

        if errors and not expect_error:
            failures += 1
            print("  !! 合法样例不应报错")
        if expect_error and not errors:
            failures += 1
            print("  !! 错误样例应当报错但未报错")

        if not expect_error:
            (OUT / f"{src_path.stem}.json").write_text(to_json(program), encoding="utf-8")
            write_html(program, OUT / f"{src_path.stem}.html",
                       title=f"AST: {src_path.name}", source=source)

    print("\n" + "=" * 70)
    if failures:
        print(f"验证失败：{failures} 个样例不符合预期")
        return 1
    print(f"验证通过：产物已输出到 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())