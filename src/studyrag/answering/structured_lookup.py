"""Answers structured-field questions (CP, language, offering cycle,
level, duration) directly from the `modules` table instead of
retrieval+generation over free text.

These five fields are deliberately never embedded in any chunk's text
— the text-only pipeline can only ever correctly decline on them, never
answer. This module makes them answerable: the LLM's only job is
phrasing an already-fully-determined fact, never deciding what the fact
is. The actual value always comes from a deterministic SQL lookup.
"""

from __future__ import annotations

import sqlite3

from openai import OpenAI
from pydantic import BaseModel, Field

from studyrag.answering.prompts import load_prompt
from studyrag.config import CHAT_MODEL
from studyrag.observability import get_openai_client

STRUCTURED_FIELDS = ["ects", "language", "cycle", "level", "duration_semesters"]

_LANGUAGE_LABELS = {"en": "English", "de": "German", "de_en": "German and English"}
_CYCLE_LABELS = {
    "winter": "winter semester only",
    "summer": "summer semester only",
    "both": "every semester",
    "irregular": "irregularly, not on a fixed cycle",
}
_LEVEL_LABELS = {"bachelor": "Bachelor", "master": "Master", "bachelor_master": "Bachelor and Master"}


class FieldLookupIntent(BaseModel):
    is_structured_field_question: bool = Field(
        description="True only if at least one of ects/language/cycle/level/duration_semesters is being asked for."
    )
    fields: list[str] = Field(description="Which of the five fields are being asked for, empty if none.")
    reason: str = Field(description="One short sentence.")


def classify_field_intent(
    question: str,
    module_title: str,
    client: OpenAI | None = None,
    model: str = CHAT_MODEL,
) -> FieldLookupIntent:
    client = client or get_openai_client()
    response = client.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": load_prompt("field_lookup_classifier_prompt")},
            {"role": "user", "content": f"Module: {module_title}\n\nQuestion: {question}"},
        ],
        response_format=FieldLookupIntent,
    )
    parsed = response.choices[0].message.parsed
    # The fields list is free-text from the model — keep only the five
    # real column names so a typo'd/invented field can't reach SQL.
    parsed.fields = [f for f in parsed.fields if f in STRUCTURED_FIELDS]
    return parsed


def format_field_value(field: str, value) -> str | None:
    """Turns a raw DB value into the display form a phrasing prompt
    should see — the DB stores canonical lowercase codes, not
    reader-facing words.
    """
    if value is None:
        return None
    if field == "ects":
        v = float(value)
        return f"{int(v) if v == int(v) else v} CP"
    if field == "language":
        return _LANGUAGE_LABELS.get(value, value)
    if field == "cycle":
        return _CYCLE_LABELS.get(value, value)
    if field == "level":
        return _LEVEL_LABELS.get(value, value)
    if field == "duration_semesters":
        n = int(value)
        return f"{n} semester" + ("" if n == 1 else "s")
    return str(value)


def lookup_module_fields(conn: sqlite3.Connection, module_row_id: int, fields: list[str]) -> dict | None:
    """Looks up the requested fields for one specific module row (the
    database's own autoincrement `id`, not the possibly-duplicated
    `module_id` — some modules are legitimately cross-listed).
    Returns None if the row doesn't exist at all.
    """
    columns = ", ".join(fields)
    row = conn.execute(
        f"SELECT title, source_id, page_start, page_end, {columns} FROM modules WHERE id = ?",
        (module_row_id,),
    ).fetchone()
    if row is None:
        return None
    columns_full = ["title", "source_id", "page_start", "page_end", *fields]
    return dict(zip(columns_full, row))
