from io import BytesIO

from docx import Document as WordDocument
from pypdf import PdfReader

from core.export import MEDIA_TYPES, export_document, export_filename
from core.export.blocks import parse_markdown

RESUME_MD = """# Casey Chen
Ottawa · [Portfolio](https://example.com) · [bad](javascript:alert(1))

## Experience
### Software Engineer — Acme (2022 – present)
- Built APIs serving **2M requests/day**.
  - Led a migration.
1. First numbered item

<script>alert("x")</script>

---
“Quotes”, café, Ελληνικά.
"""


def test_markdown_becomes_blocks_with_safe_links():
    blocks = parse_markdown(RESUME_MD)

    assert [(b.kind, b.level) for b in blocks if b.kind == "heading"] == [
        ("heading", 1),
        ("heading", 2),
        ("heading", 3),
    ]
    items = [b for b in blocks if b.kind == "list_item"]
    assert [(b.marker, b.level) for b in items] == [("•", 1), ("•", 2), ("1.", 1)]
    assert any(span.bold and span.text == "2M requests/day" for span in items[0].spans)
    links = [span.link for block in blocks for span in block.spans if span.link]
    assert links == ["https://example.com"]  # javascript: is dropped
    assert all("<script>" not in block.text for block in blocks)


def test_pdf_text_is_extractable_and_complete():
    pdf = export_document(RESUME_MD, "Casey Chen resume", "pdf")

    reader = PdfReader(BytesIO(pdf))
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert pdf.startswith(b"%PDF")
    assert len(reader.pages) == 1
    for expected in ["Casey Chen", "Software Engineer", "2M requests/day", "Led a migration", "café", "Ελληνικά"]:
        assert expected in text
    assert reader.metadata.title == "Casey Chen resume"


def test_docx_uses_word_heading_and_list_styles():
    data = export_document(RESUME_MD, "Casey Chen resume", "docx")

    document = WordDocument(BytesIO(data))
    styles = [(p.style.name, p.text) for p in document.paragraphs if p.text]
    assert ("Heading 1", "Casey Chen") in styles
    assert ("List Bullet", "Built APIs serving 2M requests/day.") in styles
    assert ("List Bullet 2", "Led a migration.") in styles
    assert ("List Number", "First numbered item") in styles
    hyperlinks = [rel.target_ref for rel in document.part.rels.values() if "hyperlink" in rel.reltype]
    assert hyperlinks == ["https://example.com"]


def test_long_documents_flow_onto_more_pages():
    long_md = "## Experience\n" + "\n".join(f"- Achievement number {i} with measurable impact." for i in range(150))

    reader = PdfReader(BytesIO(export_document(long_md, "Long", "pdf")))

    assert len(reader.pages) >= 2


def test_export_filename_is_ascii_and_safe():
    assert export_filename("Acme / Inc.", "Senior Engineer (Backend)", "resume", "v2", extension="pdf") == (
        "Acme-Inc-Senior-Engineer-Backend-resume-v2.pdf"
    )
    assert export_filename("", "", extension="docx") == "document.docx"
    assert MEDIA_TYPES["pdf"] == "application/pdf"
