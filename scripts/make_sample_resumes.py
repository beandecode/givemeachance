"""Render the demo's sample résumé (data/mock/sample_resume/casey-chen.txt) as PDF, Word and a PNG screenshot.

Live-demo guests build a profile from one of these instead of their own résumé (ADR-018), so every input format the
app accepts can be tried without personal data. Run again after editing the text: python scripts/make_sample_resumes.py
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "data/mock/sample_resume"
FONTS = ROOT / "core/export/fonts"
HEADINGS = {"SUMMARY", "EXPERIENCE", "PROJECTS", "EDUCATION", "CERTIFICATIONS", "SKILLS"}


def _lines() -> list[str]:
    return (FOLDER / "casey-chen.txt").read_text(encoding="utf-8").splitlines()


def _kind(index: int, line: str) -> str:
    if index == 0:
        return "name"
    if line in HEADINGS:
        return "heading"
    return "bullet" if line.startswith("- ") else "text"


def make_pdf() -> None:
    pdf = FPDF(format="Letter")
    pdf.set_margins(18, 16, 18)
    pdf.add_page()
    pdf.add_font("DejaVu", "", str(FONTS / "DejaVuSans.ttf"))
    pdf.add_font("DejaVu", "B", str(FONTS / "DejaVuSans-Bold.ttf"))
    for index, line in enumerate(_lines()):
        kind = _kind(index, line)
        if not line:
            pdf.ln(2)
        elif kind == "name":
            pdf.set_font("DejaVu", "B", 18)
            pdf.cell(0, 9, line, new_x="LMARGIN", new_y="NEXT")
        elif kind == "heading":
            pdf.ln(1)
            pdf.set_font("DejaVu", "B", 11)
            pdf.cell(0, 6, line, new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_font("DejaVu", "", 9.5)
            text = "• " + line[2:] if kind == "bullet" else line
            pdf.multi_cell(0, 4.8, text, new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(FOLDER / "casey-chen.pdf"))


def make_docx() -> None:
    document = Document()
    for index, line in enumerate(_lines()):
        kind = _kind(index, line)
        if not line:
            continue
        if kind == "name":
            document.add_heading(line, level=0)
        elif kind == "heading":
            document.add_heading(line.title(), level=1)
        elif kind == "bullet":
            document.add_paragraph(line[2:], style="List Bullet")
        else:
            document.add_paragraph(line)
    document.save(str(FOLDER / "casey-chen.docx"))


def make_png() -> None:
    width, margin, regular, bold = 1100, 56, 19, 22
    fonts = {
        "name": ImageFont.truetype(str(FONTS / "DejaVuSans-Bold.ttf"), 34),
        "heading": ImageFont.truetype(str(FONTS / "DejaVuSans-Bold.ttf"), bold),
        "text": ImageFont.truetype(str(FONTS / "DejaVuSans.ttf"), regular),
    }
    rows: list[tuple[str, str]] = []
    for index, line in enumerate(_lines()):
        kind = _kind(index, line)
        font = fonts["text" if kind == "bullet" else kind]
        text = "• " + line[2:] if kind == "bullet" else line
        words, current = text.split(), ""
        for word in words:  # wrap to the page width
            trial = f"{current} {word}".strip()
            if font.getlength(trial) > width - 2 * margin and current:
                rows.append((kind, current))
                current = "   " + word if kind == "bullet" else word
            else:
                current = trial
        rows.append((kind, current))
    heights = {"name": 50, "heading": 40, "text": 28, "bullet": 28}
    image = Image.new("RGB", (width, 2 * margin + sum(heights[kind] for kind, _ in rows)), "white")
    draw, y = ImageDraw.Draw(image), margin
    for kind, text in rows:
        draw.text((margin, y), text, fill=(20, 24, 31), font=fonts["text" if kind == "bullet" else kind])
        y += heights[kind]
    image.save(FOLDER / "casey-chen.png", optimize=True)


if __name__ == "__main__":
    make_pdf()
    make_docx()
    make_png()
    print(f"wrote {', '.join(p.name for p in sorted(FOLDER.iterdir()))}")
