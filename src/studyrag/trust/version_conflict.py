"""Detects when retrieved passages span more than one document and
surfaces that deterministically (not just hoping the model notices),
plus an LLM-judge check for whether a genuine conflict was handled
correctly. The real, testable case is different documents disagreeing
about the same rule -- no single document has multiple real versions
in the data fetched so far.
"""

from __future__ import annotations

from openai import OpenAI
from pydantic import BaseModel, Field

from studyrag.answering.prompts import load_prompt
from studyrag.config import CHAT_MODEL
from studyrag.observability import get_openai_client


class VersionConflictJudgement(BaseModel):
    is_true_conflict: bool = Field(
        description="True only if two+ passages state a different value for the same specific rule."
    )
    handled_correctly: bool = Field(
        description="True if a true conflict was shown explicitly with sources, or there was no conflict to invent."
    )
    reason: str = Field(description="One short sentence explaining the judgement.")


def detect_multi_source(sources: list[dict]) -> list[str]:
    """Returns the distinct source_ids among the retrieved chunks — more
    than one means the answer is being built from multiple documents.
    """
    return sorted({s["source_id"] for s in sources if s.get("source_id")})


def build_source_warning(sources: list[dict]) -> str | None:
    """A deterministic note to inject into the generation prompt when
    retrieval spans multiple documents — not relying on the model to
    notice this from the passage text alone.
    """
    distinct = detect_multi_source(sources)
    if len(distinct) < 2:
        return None
    return (
        f"NOTE: the passages below come from {len(distinct)} different documents ({', '.join(distinct)}). "
        "If any of them state a different value for the *same specific rule*, say so explicitly and name which "
        "document each value comes from. Do not treat two passages as agreeing just because they share a similar "
        "number — check whether they're actually about the same rule first."
    )


def check_conflict_handling(
    answer: str,
    sources: list[dict],
    client: OpenAI | None = None,
    model: str = CHAT_MODEL,
) -> VersionConflictJudgement:
    client = client or get_openai_client()
    passages_text = "\n\n".join(f"[{i}] ({s.get('source_id')}) {s['text']}" for i, s in enumerate(sources, start=1))
    response = client.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": load_prompt("version_conflict_judge_prompt")},
            {"role": "user", "content": f"Answer:\n{answer}\n\nPassages:\n{passages_text}"},
        ],
        response_format=VersionConflictJudgement,
    )
    return response.choices[0].message.parsed
