"""生成《编译技术》实验二实验报告（Word + Markdown）。

内容来自 content2.py（严格对应大纲的 6 条报告要求），配图来自 figures2.py。
由使用者在本地终端执行：
    python report\\build_report2.py
"""

from __future__ import annotations

import pathlib
import sys

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import content2  # noqa: E402
import figures2  # noqa: E402
from build_report import CENTER, add_picture, add_table, para  # noqa: E402

OUT_DOCX = ROOT / "report" / "实验二报告.docx"
OUT_MD = ROOT / "report" / "实验二报告.md"


def para_code(doc, text):
    """等宽字体展示代码片段：ASCII 用 Consolas，中文回退到宋体。"""
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.font.name = "Consolas"
    run.font.size = Pt(8.5)
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.get_or_add_rFonts()
    rfonts.set(qn("w:ascii"), "Consolas")
    rfonts.set(qn("w:hAnsi"), "Consolas")
    rfonts.set(qn("w:eastAsia"), "宋体")
    pf = p.paragraph_format
    pf.line_spacing = 1.12
    pf.space_after = Pt(8)
    pf.left_indent = Pt(12)
    return p


def render_docx(content, out_path: pathlib.Path) -> pathlib.Path:
    doc = Document()
    for section in doc.sections:
        section.top_margin = Cm(2.4)
        section.bottom_margin = Cm(2.4)
        section.left_margin = Cm(2.6)
        section.right_margin = Cm(2.6)

    for kind, payload in content:
        if kind == "title":
            para(doc, payload, size=18, bold=True, font="黑体", align=CENTER, space_after=16)
        elif kind == "h1":
            para(doc, payload, size=14, bold=True, font="黑体", space_after=8)
        elif kind == "h2":
            para(doc, payload, size=12.5, bold=True, font="黑体", space_after=6)
        elif kind == "h3":
            para(doc, payload, size=12, bold=True, font="黑体", space_after=6)
        elif kind == "p":
            para(doc, payload, first_indent=True)
        elif kind == "bullets":
            for item in payload:
                para(doc, "· " + item, left_indent=24, space_after=4)
        elif kind == "code":
            para_code(doc, payload)
        elif kind == "img":
            filename, caption, width_cm = payload
            add_picture(doc, filename, caption, width_cm)
        elif kind == "table":
            (header, rows, widths), caption = payload
            add_table(doc, header, rows, widths, caption)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    return out_path


def render_md(content, out_path: pathlib.Path) -> pathlib.Path:
    lines: list[str] = []
    for kind, payload in content:
        if kind == "title":
            lines += [f"# {payload}", ""]
        elif kind == "h1":
            lines += [f"## {payload}", ""]
        elif kind == "h2":
            lines += [f"### {payload}", ""]
        elif kind == "h3":
            lines += [f"#### {payload}", ""]
        elif kind == "p":
            lines += [payload, ""]
        elif kind == "bullets":
            lines += [f"- {item}" for item in payload] + [""]
        elif kind == "code":
            lines += ["```", payload, "```", ""]
        elif kind == "img":
            filename, caption, _ = payload
            lines += [f"![{caption}](figures/{filename})", "", f"*{caption}*", ""]
        elif kind == "table":
            (header, rows, _), caption = payload
            lines += [f"**{caption}**", ""]
            lines.append("| " + " | ".join(header) + " |")
            lines.append("| " + " | ".join(["---"] * len(header)) + " |")
            for row in rows:
                lines.append("| " + " | ".join(row) + " |")
            lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def main() -> int:
    figures2.main()
    print(f"报告（Word）-> {render_docx(content2.CONTENT, OUT_DOCX)}")
    print(f"报告（Markdown）-> {render_md(content2.CONTENT, OUT_MD)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())