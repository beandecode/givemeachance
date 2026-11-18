"""Render document blocks to a clean, ATS-friendly PDF (US Letter, DejaVu Sans)."""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

from core.export.blocks import Block

FONT_DIR = Path(__file__).resolve().parent / "fonts"
FAMILY = "DejaVu"
BODY_SIZE = 10
LINE_HEIGHT = 5.2  # mm for body text
HEADING_SIZES = {1: 17, 2: 12.5, 3: 11}
INDENT_PER_LEVEL = 5.5  # mm
ACCENT = (40, 64, 99)


def _new_pdf(title: str) -> FPDF:
    pdf = FPDF(format="letter", unit="mm")
    pdf.set_margins(left=18, top=16, right=18)
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_font(FAMILY, "", str(FONT_DIR / "DejaVuSans.ttf"))
    pdf.add_font(FAMILY, "B", str(FONT_DIR / "DejaVuSans-Bold.ttf"))
    pdf.add_font(FAMILY, "I", str(FONT_DIR / "DejaVuSans-Oblique.ttf"))
    # No bold-oblique face is shipped; bold wins when both are requested.
    pdf.add_font(FAMILY, "BI", str(FONT_DIR / "DejaVuSans-Bold.ttf"))
    pdf.set_title(title)
    pdf.set_creator("GivemeaChance")
    pdf.add_page()
    return pdf


def _write_spans(pdf: FPDF, block: Block, size: float, line_height: float, force_bold: bool = False) -> None:
    for span in block.spans:
        style = ("B" if span.bold or force_bold else "") + ("I" if span.italic else "")
        pdf.set_font(FAMILY, style, size)
        if span.link:
            pdf.set_text_color(*ACCENT)
            pdf.write(line_height, span.text, link=span.link)
            pdf.set_text_color(0, 0, 0)
        else:
            pdf.write(line_height, span.text)
    pdf.ln(line_height)


def render_pdf(blocks: list[Block], title: str) -> bytes:
    pdf = _new_pdf(title)
    left = pdf.l_margin
    previous = ""
    for block in blocks:
        if block.kind == "heading":
            size = HEADING_SIZES.get(block.level, BODY_SIZE + 0.5)
            pdf.ln(1.5 if block.level == 1 or previous in {"", "heading"} else 3.5)
            pdf.set_text_color(*(ACCENT if block.level == 2 else (0, 0, 0)))
            _write_spans(pdf, block, size, size * 0.5, force_bold=True)
            pdf.set_text_color(0, 0, 0)
            if block.level == 2:
                pdf.set_draw_color(*ACCENT)
                pdf.set_line_width(0.3)
                pdf.line(left, pdf.get_y() + 0.6, pdf.w - pdf.r_margin, pdf.get_y() + 0.6)
                pdf.ln(2.2)
            else:
                pdf.ln(0.8)
        elif block.kind == "list_item":
            indent = left + INDENT_PER_LEVEL * (block.level - 1)
            pdf.set_x(indent)
            pdf.set_font(FAMILY, "", BODY_SIZE)
            marker_width = 4.5 if block.marker in {"", "•"} else 6
            pdf.cell(marker_width, LINE_HEIGHT, block.marker)
            pdf.set_left_margin(indent + marker_width)
            _write_spans(pdf, block, BODY_SIZE, LINE_HEIGHT)
            pdf.set_left_margin(left)
            pdf.ln(0.6)
        elif block.kind == "rule":
            pdf.ln(1.5)
            pdf.set_draw_color(180, 180, 180)
            pdf.set_line_width(0.2)
            pdf.line(left, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.ln(2.5)
        else:
            _write_spans(pdf, block, BODY_SIZE, LINE_HEIGHT)
            pdf.ln(2)
        previous = block.kind
    return bytes(pdf.output())
