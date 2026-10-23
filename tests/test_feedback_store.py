"""Feedback capture -- pure SQLite CRUD, no LLM call."""

from __future__ import annotations

import json
import sqlite3

from studyrag.api.feedback_store import save_feedback


def test_save_feedback_persists_all_fields(tmp_path):
    db_path = tmp_path / "feedback.db"
    feedback_id = save_feedback(
        question="How many CP is X worth?",
        answer="X is worth 4 CP.",
        sources=[{"kind": "module", "module_id": "123"}],
        rating="down",
        comment="Wrong module.",
        db_path=db_path,
    )

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT question, answer, sources_json, rating, comment FROM feedback WHERE id = ?", (feedback_id,)).fetchone()
    conn.close()

    assert row[0] == "How many CP is X worth?"
    assert row[1] == "X is worth 4 CP."
    assert json.loads(row[2]) == [{"kind": "module", "module_id": "123"}]
    assert row[3] == "down"
    assert row[4] == "Wrong module."


def test_save_feedback_without_comment(tmp_path):
    db_path = tmp_path / "feedback.db"
    feedback_id = save_feedback(question="q", answer="a", sources=[], rating="up", db_path=db_path)

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT comment FROM feedback WHERE id = ?", (feedback_id,)).fetchone()
    conn.close()

    assert row[0] is None
