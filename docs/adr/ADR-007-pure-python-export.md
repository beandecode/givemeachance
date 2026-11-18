# ADR-007: Pure-Python PDF/DOCX export (fpdf2 + python-docx) instead of WeasyPrint

Date: 2026-10-20
Status: Accepted

## Context

Generated resumes and cover letters must be downloadable as PDF and DOCX (roadmap Phase 2). The roadmap proposed
WeasyPrint (HTML/CSS → PDF) for typography. WeasyPrint needs the Pango text stack: about 25 Homebrew libraries on
a developer's Mac for local development and tests, and ~60 MB of system packages in the Docker image. Avoiding system
installs was a requirement.

## Decision

- Parse Markdown once with markdown-it-py into a small block model (`core/export/blocks.py`): headings, paragraphs,
  nested bullet/numbered lists, rules, bold/italic/links. Raw HTML is dropped; only http(s)/mailto links are kept.
- Render PDF with fpdf2 (US Letter, single column) using the bundled DejaVu Sans fonts (`core/export/fonts/`, license
  included) so typographic punctuation, accents, Greek and Cyrillic render; render DOCX with python-docx using Word's
  built-in heading and list styles and real hyperlinks.
- Tests check extractable PDF text (pypdf), page flow, DOCX styles and links.

## Consequences

1. Identical output locally, in CI and in Docker; no system libraries; the image stays small.
2. Layout is simple and ATS-friendly, but less flexible than CSS (no multi-column templates). Adding templates later
   means extending the renderers, or revisiting WeasyPrint if richer design becomes a requirement.
3. No CJK glyphs in DejaVu Sans; supporting them needs an additional font (e.g. Noto Sans CJK, ~16 MB).
