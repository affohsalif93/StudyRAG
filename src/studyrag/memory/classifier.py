"""Decides whether a question reveals a durable fact worth remembering,
for the core fixed pipeline — the agent-bound `remember`/`forget` tools
(tools.py) let the chair-lookup agent decide this itself mid-conversation,
but the core pipeline isn't an agent, so it needs its own classify-then-
write step, same shape as structured_lookup's and chair_lookup's
classifiers (a narrow, cheap LLM call deciding *whether/what*, with the
actual write staying a deterministic function call, never left to the
model to execute itself).
"""

from __future__ import annotations

from openai import OpenAI
from pydantic import BaseModel, Field

from studyrag.answering.prompts import load_prompt
from studyrag.config import CHAT_MODEL
from studyrag.observability import get_openai_client


class MemoryFact(BaseModel):
    key: str = Field(description="Short snake_case key, reusing an existing one when updating a known fact.")
    value: str = Field(description="The fact, as a short clear statement.")


class MemoryIntent(BaseModel):
    should_remember: bool = Field(description="True only if the question itself states at least one durable fact about the student.")
    facts: list[MemoryFact] = Field(
        default_factory=list,
        description="One entry per distinct fact — never bundle unrelated facts (e.g. a completed module and a career goal) into a single key.",
    )
    reason: str = Field(description="One short sentence.")


def classify_memory_intent(
    question: str,
    existing_facts: dict[str, str],
    client: OpenAI | None = None,
    model: str = CHAT_MODEL,
) -> MemoryIntent:
    client = client or get_openai_client()
    known = "\n".join(f"- {k}: {v}" for k, v in existing_facts.items()) or "(nothing remembered yet)"
    response = client.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": load_prompt("memory_classifier_prompt")},
            {"role": "user", "content": f"Already remembered:\n{known}\n\nQuestion: {question}"},
        ],
        response_format=MemoryIntent,
    )
    return response.choices[0].message.parsed
