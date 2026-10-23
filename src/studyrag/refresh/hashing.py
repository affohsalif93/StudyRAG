"""Content hashing, at both the whole-document level (already tracked
in data/raw/sources.json) and per-page -- the finer granularity a diff
report needs to say which page changed.
"""

from __future__ import annotations

import hashlib

from studyrag.ingestion.pdf_text import PAGE_BREAK


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def split_pages(text: str) -> list[str]:
    """Splits pdftotext's form-feed-separated output into one string per
    page, each stripped -- pdftotext pads page text with whitespace that
    varies run to run without the content changing, which would
    otherwise make every page look "changed."

    pdftotext emits a trailing form-feed after the last page, which
    would otherwise split into one spurious empty "page" at the end --
    strip exactly that one trailing separator first.
    """
    if text.endswith(PAGE_BREAK):
        text = text[: -len(PAGE_BREAK)]
    return [page.strip() for page in text.split(PAGE_BREAK)]


def hash_pages(text: str) -> list[str]:
    """One SHA-256 hex digest per page, in page order."""
    return [hash_bytes(page.encode("utf-8")) for page in split_pages(text)]
