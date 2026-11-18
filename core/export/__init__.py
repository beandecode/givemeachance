"""Export generated Markdown documents to PDF or DOCX (pure Python, no system libraries)."""

from __future__ import annotations

import re
from typing import Literal

from core.export.blocks import parse_markdown
from core.export.docx import render_docx
from core.export.pdf import render_pdf

ExportFormat = Literal["pdf", "docx"]
MEDIA_TYPES: dict[str, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def export_document(content_md: str, title: str, fmt: ExportFormat) -> bytes:
    blocks = parse_markdown(content_md)
    return render_pdf(blocks, title) if fmt == "pdf" else render_docx(blocks, title)


def export_filename(*parts: str, extension: str) -> str:
    """ASCII, filesystem-safe name such as `Acme-Backend-Engineer-resume-v2.pdf`."""
    words = [re.sub(r"[^A-Za-z0-9]+", "-", part).strip("-") for part in parts]
    stem = "-".join(word for word in words if word)[:120] or "document"
    return f"{stem}.{extension}"
