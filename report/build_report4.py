"""生成《编译技术》实验四实验报告（Word + Markdown）。

内容来自 content4.py（对应大纲 6 条要求 + 难点 + 4 道思考题），
配图来自 figures4.py。由使用者在本地终端执行：
    python report\\build_report4.py
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import content4  # noqa: E402
import figures4  # noqa: E402
from build_report2 import render_docx, render_md  # noqa: E402

OUT_DOCX = ROOT / "report" / "实验四报告.docx"
OUT_MD = ROOT / "report" / "实验四报告.md"


def main() -> int:
    figures4.main()
    print(f"报告（Word）-> {render_docx(content4.CONTENT, OUT_DOCX)}")
    print(f"报告（Markdown）-> {render_md(content4.CONTENT, OUT_MD)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())