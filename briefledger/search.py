"""Literal FTS query construction and source-preserving chunk boundaries."""

import re
from dataclasses import dataclass

from .errors import StoreError


@dataclass(frozen=True)
class Chunk:
    text: str
    start: int
    end: int
    line_start: int
    line_end: int
    heading: str


def safe_query(query: str) -> str:
    if not isinstance(query, str) or not query.strip() or len(query) > 160:
        raise StoreError("Search must contain 1–160 characters.")
    terms = re.findall(r"[^\W_]+", query, flags=re.UNICODE)
    if not terms or len(terms) > 12:
        raise StoreError("Use 1–12 searchable words. Symbols alone cannot be searched.")
    # Every term is a literal quoted string. User input never enters the FTS operator grammar.
    return " AND ".join('"' + term.replace('"', '""') + '"' for term in terms)


def chunk_text(text: str) -> list[Chunk]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + 1400)
        if end < len(text):
            boundary = text.rfind("\n", start + 700, end)
            if boundary == -1:
                boundary = text.rfind(" ", start + 1000, end)
            if boundary != -1:
                end = boundary + 1
        body = text[start:end]
        if body.strip():
            headings = re.findall(r"^#{1,6}\s+(.+)$", text[: start + 1], re.MULTILINE)
            if not headings:
                headings = re.findall(r"^#{1,6}\s+(.+)$", body, re.MULTILINE)[:1]
            chunks.append(
                Chunk(
                    text=body,
                    start=start,
                    end=end,
                    line_start=text.count("\n", 0, start) + 1,
                    line_end=text.count("\n", 0, end - int(body.endswith("\n"))) + 1,
                    heading=headings[-1][:120] if headings else "Document text",
                )
            )
        if end == len(text):
            break
        next_start = max(start + 1, end - 180)
        # Prefer an overlap starting at a source line, then a word; hard slices cover long tokens.
        newline = text.find("\n", next_start, end - 1)
        space = text.find(" ", next_start, end - 1)
        if newline != -1:
            next_start = newline + 1
        elif space != -1:
            next_start = space + 1
        start = next_start
    return chunks


def snippet_segments(text: str) -> list[dict]:
    """Return text and match flags; the browser never interprets source HTML."""
    result = []
    marked = False
    for part in re.split("([\x01\x02])", text):
        if part == "\x01":
            marked = True
        elif part == "\x02":
            marked = False
        elif part:
            result.append({"text": part, "match": marked})
    return result
