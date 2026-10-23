"""The size-threshold secondary split on top of structure-aware
chunking -- every sub-chunk must still carry its module/rule context,
never a bare fragment.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from studyrag.retrieval.chunks import _MAX_CHUNK_CHARS, _split_body, build_module_chunks, build_rule_chunks

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "studyrag.db"


def test_short_body_is_not_split():
    pieces = _split_body("Module X — content", "A short description.")
    assert pieces == ["Module X — content: A short description."]


def test_long_body_is_split_into_multiple_prefixed_pieces():
    long_body = "Sentence number %d talks about a different topic each time. " * 100
    pieces = _split_body("Module Y — content", long_body)

    assert len(pieces) > 1
    for i, piece in enumerate(pieces, start=1):
        assert piece.startswith(f"Module Y — content (part {i} of {len(pieces)}):")
        assert len(piece) <= _MAX_CHUNK_CHARS + 200  # some overshoot from separators is expected


def test_split_pieces_overlap_so_no_idea_is_fully_cut_off():
    long_body = "UNIQUEMARKER" + ("filler word " * 300) + "ANOTHERMARKER" + ("filler word " * 300)
    pieces = _split_body("Module Z — content", long_body)

    assert any("UNIQUEMARKER" in p for p in pieces)
    assert any("ANOTHERMARKER" in p for p in pieces)


@pytest.mark.skipif(not DB_PATH.exists(), reason="no built database in this checkout")
def test_module_chunks_carry_document_level_metadata():
    conn = sqlite3.connect(DB_PATH)
    try:
        chunks = build_module_chunks(conn)
        assert chunks, "expected at least one module chunk"
        for chunk in chunks:
            assert chunk["doc_type"] == "module_handbook"
            assert chunk["language"] in ("en", "de")
    finally:
        conn.close()


@pytest.mark.skipif(not DB_PATH.exists(), reason="no built database in this checkout")
def test_rule_chunks_carry_document_level_metadata():
    conn = sqlite3.connect(DB_PATH)
    try:
        chunks = build_rule_chunks(conn)
        assert chunks, "expected at least one rule chunk"
        doc_types = {chunk["doc_type"] for chunk in chunks}
        assert doc_types <= {"po", "uepo"}
        for chunk in chunks:
            assert chunk["language"] in ("en", "de")
    finally:
        conn.close()
