"""An LLM-based correctness judge, meant to replace the crude keyword
proxy (`eval/_common.py:is_correct_proxy`). This module is the judge
itself; `eval/run_ai_judge.py` runs it over the eval set,
`eval/grade_human.py` collects independent human grades on the same
answers, and `eval/measure_agreement.py` compares the two.
"""

from __future__ import annotations

from openai import OpenAI
from pydantic import BaseModel, Field

from studyrag.answering.chat import DISCLAIMER
from studyrag.answering.prompts import load_prompt
from studyrag.config import CHAT_MODEL
from studyrag.observability import get_openai_client


class CorrectnessJudgement(BaseModel):
    correct: bool = Field(description="True if the answer is correct per the rubric.")
    reason: str = Field(description="One short sentence explaining the judgement.")


def judge_correctness(
    question: str,
    answer: str,
    sources: list[dict],
    client: OpenAI | None = None,
    model: str = CHAT_MODEL,
) -> CorrectnessJudgement:
    """Judges the full answer against the passages it was actually given
    — not against a stored "gold answer" string, so the judge can be run
    on any question without needing one hand-written per question.
    """
    client = client or get_openai_client()
    answer_without_disclaimer = answer.split(DISCLAIMER)[0]
    passages_text = "\n\n".join(f"[{i}] {s['text']}" for i, s in enumerate(sources, start=1))
    response = client.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": load_prompt("answer_correctness_judge_prompt")},
            {
                "role": "user",
                "content": f"Question: {question}\n\nPassages:\n{passages_text}\n\nAnswer: {answer_without_disclaimer}",
            },
        ],
        response_format=CorrectnessJudgement,
    )
    return response.choices[0].message.parsed
