"""A greeting like "hi" retrieves nothing relevant and used to fall into
the same ABSTENTION_THRESHOLD branch as a genuine unanswerable regulation
question, producing the same cold "not found in the documents" message.
This classifier only runs inside that already-triggered low-confidence
branch (see chat.py's _answer_question_impl) — it adds no cost to the
normal, confidently-retrieved case, since it never runs for those.
"""

from __future__ import annotations

from typing import Literal

from openai import OpenAI
from pydantic import BaseModel, Field

from studyrag.answering.prompts import load_prompt
from studyrag.config import CHAT_MODEL
from studyrag.observability import get_openai_client


class QueryIntent(BaseModel):
    category: Literal["chitchat", "off_topic", "on_topic"] = Field(
        description="chitchat: greeting/small talk. off_topic: clearly unrelated to the degree program. "
        "on_topic: a genuine but unanswered-from-the-corpus question about the student's studies."
    )
    reply: str = Field(
        description="A natural reply, only when category is 'chitchat'. Empty string otherwise — "
        "off_topic and on_topic use a fixed message instead."
    )
    reason: str = Field(description="One short sentence.")


def classify_query_intent(question: str, client: OpenAI | None = None, model: str = CHAT_MODEL) -> QueryIntent:
    client = client or get_openai_client()
    response = client.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": load_prompt("query_intent_classifier_prompt")},
            {"role": "user", "content": f"Question: {question}"},
        ],
        response_format=QueryIntent,
    )
    return response.choices[0].message.parsed
