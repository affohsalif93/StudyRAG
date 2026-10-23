"""Feedback capture — thumbs up/down with an optional comment, stored
so wrong answers can be flagged and later added to eval/questions.json.
Its own SQLite file (data/feedback.db): genuinely new user-submitted
data that must never be touched by the "safe to wipe and rebuild from
scratch" derived tables in data/studyrag.db.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_DB_PATH = REPO_ROOT / "data" / "feedback.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    sources_json TEXT NOT NULL,
    rating TEXT NOT NULL CHECK (rating IN ('up', 'down')),
    comment TEXT,
    created_at TEXT NOT NULL
);
"""


def save_feedback(
    question: str,
    answer: str,
    sources: list[dict],
    rating: str,
    comment: str | None = None,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> int:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(_SCHEMA)
        cursor = conn.execute(
            "INSERT INTO feedback (question, answer, sources_json, rating, comment, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                question,
                answer,
                json.dumps(sources, ensure_ascii=False),
                rating,
                comment,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()
