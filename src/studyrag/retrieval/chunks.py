"""Build embeddable chunks from the modules and rules tables — both feed
one combined retrieval index, not two separate ones.

Each module becomes up to two chunks, grouped by what a question is
actually asking: "what does this teach" vs "what do I need first" — not
one whole-module blob, not one chunk per individual field. Each operative
(non-template) PO/ÜPO rule becomes one chunk, prefixed with its
document/§/Abs. context.

Module chunk ids use modules.id (the autoincrement primary key), never
module_id — module_id is not unique (one real module is legitimately
cross-listed twice under two areas). Rule chunk ids use rules.id likewise.
"""

from __future__ import annotations

import re
import sqlite3
from typing import TypedDict

from langchain_text_splitters import RecursiveCharacterTextSplitter


class Chunk(TypedDict):
    chunk_id: str
    kind: str  # "module" | "rule"
    module_row_id: int
    module_id: str
    field_group: str  # "teaches" | "prerequisites"
    text: str  # the literal string to embed, title-prefixed
    title: str
    area: str | None
    source_id: str
    doc_type: str  # "module_handbook" | "po" | "uepo" — document-level metadata filtering
    language: str  # "en" | "de" — the SOURCE document's language, from sources.language; distinct
    # from a module's own per-module language field (e.g. "de_en"), which isn't surfaced here
    page_start: int | None


_PLACEHOLDER_VALUES = {"none.", "none", "-", ""}

# Most module/rule text is already well under this, but the long tail
# goes up to ~5,500 chars, occasionally bundling two distinct lecture
# syllabi under a single module record. One embedding vector averaging
# over that much genuinely different content is worse than splitting it --
# this is a second, size-triggered split on top of the module/field-group
# structure, not a replacement for it.
_MAX_CHUNK_CHARS = 1500
_CHUNK_OVERLAP = 150
_splitter = RecursiveCharacterTextSplitter(chunk_size=_MAX_CHUNK_CHARS, chunk_overlap=_CHUNK_OVERLAP)


def _split_body(prefix: str, body: str) -> list[str]:
    """Returns one or more embeddable strings, each still carrying
    `prefix` — a sub-chunk's text must never be a bare fragment with no
    module/rule context, same principle as the title-prefixing decision
    this builds on. Only actually splits when the combined text would
    exceed the threshold; the common (short) case is untouched.
    """
    full_text = f"{prefix}: {body}"
    if len(full_text) <= _MAX_CHUNK_CHARS:
        return [full_text]
    pieces = _splitter.split_text(body)
    n = len(pieces)
    return [f"{prefix} (part {i} of {n}): {piece}" for i, piece in enumerate(pieces, start=1)]


def _join_present(*parts: str | None) -> str | None:
    """Drops parts that are empty or a bare "None."-style placeholder --
    pure noise to embed otherwise."""
    present = [p.strip() for p in parts if p and p.strip().lower() not in _PLACEHOLDER_VALUES]
    if not present:
        return None
    return "\n".join(present)


def build_module_chunks(conn: sqlite3.Connection) -> list[Chunk]:
    rows = conn.execute(
        """
        SELECT m.id, m.module_id, m.title, m.content, m.learning_objectives,
               m.prerequisites, m.recommended_requirements, m.area, m.source_id, m.page_start,
               s.doc_type, s.language
        FROM modules m JOIN sources s ON m.source_id = s.id
        """
    ).fetchall()

    chunks: list[Chunk] = []
    for row_id, module_id, title, content, learning_objectives, prerequisites, recommended_requirements, area, source_id, page_start, doc_type, language in rows:
        title = title or f"module {module_id}"
        base_metadata = {
            "kind": "module",
            "module_row_id": row_id,
            "module_id": module_id,
            "title": title,
            "area": area,
            "source_id": source_id,
            "doc_type": doc_type,
            "language": language,
            "page_start": page_start,
        }

        teaches_text = _join_present(content, learning_objectives)
        if teaches_text:
            pieces = _split_body(f"{title} — content and learning objectives", teaches_text)
            for i, text in enumerate(pieces, start=1):
                chunk_id = f"{row_id}_teaches" if len(pieces) == 1 else f"{row_id}_teaches_p{i}"
                chunks.append({**base_metadata, "chunk_id": chunk_id, "field_group": "teaches", "text": text})

        prereq_text = _join_present(prerequisites, recommended_requirements)
        if prereq_text:
            pieces = _split_body(f"{title} — prerequisites", prereq_text)
            for i, text in enumerate(pieces, start=1):
                chunk_id = f"{row_id}_prerequisites" if len(pieces) == 1 else f"{row_id}_prerequisites_p{i}"
                chunks.append({**base_metadata, "chunk_id": chunk_id, "field_group": "prerequisites", "text": text})

    return chunks


_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_for_dupe_check(s: str) -> str:
    return _WHITESPACE_RE.sub("", s).lower()


def build_rule_chunks(conn: sqlite3.Connection) -> list[dict]:
    """One chunk per operative (non-template) PO/ÜPO rule, prefixed with
    its document/§/Abs. context so retrieval can tell rules from different
    documents or paragraphs apart — same title-prefix principle as modules.
    Template/example annexes (is_template_example = 1) are excluded, as are
    "preamble" pieces (absatz IS NULL) whose text is just the § heading
    repeated verbatim with nothing else -- pure noise duplicating
    paragraph_title.
    """
    rows = conn.execute(
        """
        SELECT r.id, r.source_id, s.name, r.paragraph, r.paragraph_title, r.absatz, r.text,
               s.doc_type, s.language
        FROM rules r JOIN sources s ON r.source_id = s.id
        WHERE r.is_template_example = 0 AND r.text IS NOT NULL AND r.text != ''
        """
    ).fetchall()

    chunks: list[dict] = []
    for row_id, source_id, source_name, paragraph, paragraph_title, absatz, text, doc_type, language in rows:
        heading_only = f"§{paragraph}{paragraph_title or ''}"
        if absatz is None and _normalize_for_dupe_check(text) == _normalize_for_dupe_check(heading_only):
            continue

        heading = f"{source_name} § {paragraph} {paragraph_title}" if paragraph_title else f"{source_name} § {paragraph}"
        if absatz:
            heading += f", Abs. {absatz}"

        base_metadata = {
            "kind": "rule",
            "rule_row_id": row_id,
            "source_id": source_id,
            "paragraph": paragraph,
            "absatz": absatz,
            "title": heading,
            "doc_type": doc_type,
            "language": language,
        }
        pieces = _split_body(heading, text)
        for i, piece_text in enumerate(pieces, start=1):
            chunk_id = f"rule_{row_id}" if len(pieces) == 1 else f"rule_{row_id}_p{i}"
            chunks.append({**base_metadata, "chunk_id": chunk_id, "text": piece_text})
    return chunks
