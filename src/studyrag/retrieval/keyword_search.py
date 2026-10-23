"""Keyword search via SQLite's built-in FTS5 extension — BM25 ranking, no
separate search engine needed. Operates over the exact same chunks the
vector store embeds (chunks_fts, populated by
src/studyrag/db/loader.py:load_fts_index from
src/studyrag/retrieval/chunks.py's output), so results can be fused with
vector search by chunk_id in hybrid.py.
"""

from __future__ import annotations

import re
import sqlite3

# FTS5's query syntax gives special meaning to characters like -, ", *,
# : and parentheses — a raw natural-language question ("What's the
# maximum CP...?") can hit a syntax error. Extracting plain word tokens
# and quoting each one neutralizes that: a quoted token has no special
# meaning in FTS5 syntax, whatever punctuation the question contained.
_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _sanitize_query(question: str) -> str:
    """Builds an FTS5 MATCH expression that ORs every word in the
    question — OR, not FTS5's default AND, because BM25 ranking already
    handles "matches fewer terms -> ranks lower" on its own; requiring
    every term to appear would make any one unmatched word (a typo, a
    term literally absent from the corpus) kill the whole match.
    """
    words = _WORD_RE.findall(question)
    if not words:
        return '""'
    return " OR ".join(f'"{w}"' for w in words)


def keyword_search(conn: sqlite3.Connection, question: str, k: int = 10) -> list[tuple[str, float]]:
    """Returns (chunk_id, score) pairs, best match first, higher = better.

    FTS5's bm25() returns a *negative* value where more negative = a
    better match — the opposite convention from cosine similarity (higher
    = better) used everywhere else in this project. Negated here so every
    caller can treat "higher = better" uniformly; verified directly
    against FTS5's own docs behavior, not assumed.
    """
    query = _sanitize_query(question)
    cursor = conn.execute(
        "SELECT chunk_id, bm25(chunks_fts) AS rank FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?",
        (query, k),
    )
    return [(chunk_id, -rank) for chunk_id, rank in cursor.fetchall()]
