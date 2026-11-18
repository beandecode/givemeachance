"""Render document blocks to a Word document using built-in styles (ATS-friendly)."""

from __future__ import annotations

from io import BytesIO

from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from docx.text.paragraph import Paragraph

from core.export.blocks import Block, Span

ACCENT = RGBColor(0x28, 0x40, 0x63)


def _add_hyperlink(paragraph: Paragraph, span: Span) -> None:
    assert span.link is not None
    rel_id = paragraph.part.relate_to(span.link, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), rel_id)
    run = OxmlElement("w:r")
    properties = OxmlElement("w:rPr")
    for tag, value in (("w:color", "284063"), ("w:u", "single")):
        element = OxmlElement(tag)
        element.set(qn("w:val"), value)
        properties.append(element)
    if span.bold:
        properties.append(OxmlElement("w:b"))
    if span.italic:
        properties.append(OxmlElement("w:i"))
    run.append(properties)
    text = OxmlElement("w:t")
    text.text = span.text
    text.set(qn("xml:space"), "preserve")
    run.append(text)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def _add_spans(paragraph: Paragraph, spans: list[Span]) -> None:
    for span in spans:
        if span.link:
            _add_hyperlink(paragraph, span)
            continue
        run = paragraph.add_run(span.text)
        run.bold = span.bold or None
        run.italic = span.italic or None


def render_docx(blocks: list[Block], title: str) -> bytes:
    document = Document()
    document.core_properties.title = title
    document.core_properties.author = ""
    normal = document.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10.5)
    for block in blocks:
        if block.kind == "heading":
            heading = document.add_heading(level=min(block.level, 4))
            _add_spans(heading, block.spans)
            for run in heading.runs:
                run.font.color.rgb = ACCENT
        elif block.kind == "list_item":
            numbered = block.marker[:-1].isdigit() if block.marker else False
            base = "List Number" if numbered else "List Bullet"
            style = base if block.level <= 1 else f"{base} {min(block.level, 3)}"
            paragraph = document.add_paragraph(style=style)
            _add_spans(paragraph, block.spans)
        elif block.kind == "rule":
            document.add_paragraph("")
        else:
            _add_spans(document.add_paragraph(), block.spans)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()
