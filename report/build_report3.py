"""生成《编译技术》实验三实验报告（Word + Markdown）。

内容来自 content3.py（严格对应大纲的 6 条报告要求），配图来自 figures3.py。
由使用者在本地终端执行：
    python report\\build_report3.py
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import content3  # noqa: E402
import figures3  # noqa: E402
from build_report2 import render_docx, render_md  # noqa: E402

OUT_DOCX = ROOT / "report" / "实验三报告.docx"
OUT_MD = ROOT / "report" / "实验三报告.md"


def main() -> int:
    figures3.main()
    print(f"报告（Word）-> {render_docx(content3.CONTENT, OUT_DOCX)}")
    print(f"报告（Markdown）-> {render_md(content3.CONTENT, OUT_MD)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())