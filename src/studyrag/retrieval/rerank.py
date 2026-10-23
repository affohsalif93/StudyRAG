"""Reranking — fetch a larger candidate pool cheaply by cosine
similarity, then reorder with the same LLM used for every other judgment
call in this project rather than a new cross-encoder dependency, and
keep the best k.

Reuses each candidate's own cosine `score` unchanged after reordering --
never a new LLM-derived score -- so the abstention threshold (calibrated
against cosine similarity) keeps working unchanged; reranking only
changes which chunks get selected and in what order.
"""

from __future__ import annotations

from typing import Any, Callable

from openai import OpenAI
from pydantic import BaseModel, Field

from studyrag.answering.prompts import load_prompt
from studyrag.config import CHAT_MODEL
from studyrag.observability import get_openai_client


class RerankResult(BaseModel):
    top_indices: list[int] = Field(description="Candidate numbers (1-based), best first, most relevant to least.")


def rerank(
    question: str,
    candidates: list[Any],
    k: int = 5,
    client: OpenAI | None = None,
    model: str = CHAT_MODEL,
    get_text: Callable[[Any], str] = lambda c: c["text"],
) -> list[Any]:
    """Returns up to `k` of `candidates`, reordered by the LLM's
    judgment of relevance to `question`. If there are k or fewer
    candidates to begin with, there's nothing meaningful to reorder —
    returned unchanged, no LLM call spent. `get_text` extracts the
    embeddable text from one candidate — defaults to the bare
    pipeline's plain dicts (`c["text"]`); the LangChain pipeline passes
    `lambda d: d.page_content` for its `Document` objects instead.
    """
    if len(candidates) <= k:
        return candidates

    client = client or get_openai_client()
    passages_block = "\n\n".join(f"[{i}] {get_text(c)}" for i, c in enumerate(candidates, start=1))
    response = client.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": load_prompt("rerank_prompt")},
            {"role": "user", "content": f"Question: {question}\n\nCandidates:\n{passages_block}"},
        ],
        response_format=RerankResult,
    )
    parsed = response.choices[0].message.parsed

    # Never trust the model's indices blindly: keep only valid, in-range,
    # deduplicated ones, then fill any remaining slots from the original
    # cosine-rank order if the model returned fewer than k or an invalid one.
    seen: set[int] = set()
    picked = []
    for idx in parsed.top_indices:
        if 1 <= idx <= len(candidates) and idx not in seen:
            seen.add(idx)
            picked.append(candidates[idx - 1])
        if len(picked) == k:
            break
    if len(picked) < k:
        for i, c in enumerate(candidates, start=1):
            if i not in seen:
                picked.append(c)
                seen.add(i)
            if len(picked) == k:
                break
    return picked
