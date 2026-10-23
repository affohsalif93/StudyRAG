"""The deterministic half of structured-field lookup -- value
formatting and the SQL lookup itself never involve an LLM call.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from studyrag.answering.structured_lookup import format_field_value, lookup_module_fields

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "studyrag.db"


@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("ects", 4.0, "4 CP"),
        ("ects", 4.5, "4.5 CP"),
        ("language", "en", "English"),
        ("language", "de_en", "German and English"),
        ("cycle", "irregular", "irregularly, not on a fixed cycle"),
        ("cycle", "winter", "winter semester only"),
        ("level", "bachelor_master", "Bachelor and Master"),
        ("duration_semesters", 1, "1 semester"),
        ("duration_semesters", 2, "2 semesters"),
        ("ects", None, None),
    ],
)
def test_format_field_value(field, value, expected):
    assert format_field_value(field, value) == expected


@pytest.mark.skipif(not DB_PATH.exists(), reason="no built database in this checkout")
def test_lookup_module_fields_returns_real_values_for_knowledge_graphs():
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute("SELECT id FROM modules WHERE module_id = '1212675'").fetchone()
        if row is None:
            pytest.skip("Knowledge Graphs module not present in this checkout's database")
        module_row_id = row[0]

        result = lookup_module_fields(conn, module_row_id, ["ects", "language", "cycle"])

        assert result["title"] == "Knowledge Graphs"
        assert result["ects"] == 4.0
        assert result["language"] == "en"
        assert result["cycle"] == "both"
    finally:
        conn.close()


@pytest.mark.skipif(not DB_PATH.exists(), reason="no built database in this checkout")
def test_lookup_module_fields_returns_none_for_a_nonexistent_row():
    conn = sqlite3.connect(DB_PATH)
    try:
        result = lookup_module_fields(conn, 999_999_999, ["ects"])
        assert result is None
    finally:
        conn.close()
