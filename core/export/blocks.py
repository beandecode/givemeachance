"""Markdown → a small block model shared by the PDF and DOCX renderers.

Only what resumes and cover letters use: headings, paragraphs, (nested) bullet and numbered
lists, horizontal rules, and inline bold / italic / code / links. Raw HTML is recognized and dropped
(PDF/DOCX never render it; this only keeps stray tags out of the document).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from markdown_it import MarkdownIt
from markdown_it.token import Token


@dataclass(frozen=True)
class Span:
    text: str
    bold: bool = False
    italic: bool = False
    link: str | None = None


@dataclass
class Block:
    kind: str  # "heading" | "paragraph" | "list_item" | "rule"
    spans: list[Span] = field(default_factory=list)
    level: int = 0  # heading level (1-6) or list nesting depth (1-based)
    marker: str = ""  # "•" or "3." for list items

    @property
    def text(self) -> str:
        return "".join(span.text for span in self.spans)


_PARSER = MarkdownIt("commonmark", {"html": True}).disable("image")
_SAFE_SCHEMES = ("http://", "https://", "mailto:")


def _spans(inline: Token) -> list[Span]:
    spans: list[Span] = []
    bold = italic = 0
    link: str | None = None
    for child in inline.children or []:
        if child.type == "strong_open":
            bold += 1
        elif child.type == "strong_close":
            bold -= 1
        elif child.type == "em_open":
            italic += 1
        elif child.type == "em_close":
            italic -= 1
        elif child.type == "link_open":
            href = str(child.attrs.get("href", ""))
            link = href if href.startswith(_SAFE_SCHEMES) else None
        elif child.type == "link_close":
            link = None
        elif child.type in {"text", "code_inline"}:
            spans.append(Span(child.content, bold=bold > 0, italic=italic > 0, link=link))
        elif child.type in {"softbreak", "hardbreak"}:
            spans.append(Span(" " if child.type == "softbreak" else "\n", bold=bold > 0, italic=italic > 0))
    return [span for span in spans if span.text]


def parse_markdown(markdown: str) -> list[Block]:
    blocks: list[Block] = []
    lists: list[dict] = []  # stack of {"ordered": bool, "next": int}
    pending_marker = ""
    for index, token in enumerate(tokens := _PARSER.parse(markdown or "")):
        if token.type == "heading_open":
            blocks.append(Block("heading", _spans(tokens[index + 1]), level=int(token.tag[1])))
        elif token.type in {"bullet_list_open", "ordered_list_open"}:
            start = int(token.attrs.get("start", 1) or 1)
            lists.append({"ordered": token.type == "ordered_list_open", "next": start})
        elif token.type in {"bullet_list_close", "ordered_list_close"}:
            lists.pop()
        elif token.type == "list_item_open":
            current = lists[-1]
            pending_marker = f"{current['next']}." if current["ordered"] else "•"
            current["next"] += 1
        elif token.type == "inline" and tokens[index - 1].type == "paragraph_open":
            if lists and pending_marker:
                blocks.append(Block("list_item", _spans(token), level=len(lists), marker=pending_marker))
                pending_marker = ""
            elif lists:  # continuation paragraph inside a list item
                blocks.append(Block("list_item", _spans(token), level=len(lists)))
            else:
                blocks.append(Block("paragraph", _spans(token)))
        elif token.type == "hr":
            blocks.append(Block("rule"))
        elif token.type in {"fence", "code_block"}:
            blocks.append(Block("paragraph", [Span(token.content.rstrip("\n"))]))
    return [block for block in blocks if block.kind == "rule" or block.text.strip()]
