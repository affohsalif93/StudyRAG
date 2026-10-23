"""A pre-gate deciding whether a question the core pipeline couldn't
answer is even plausibly answerable by a chair's website — run before
invoking the agent, so a chair lookup is never attempted for things no
chair page could have (tuition fees, library hours, exam regulations
the core pipeline already checked).
"""

from __future__ import annotations

from openai import OpenAI
from pydantic import BaseModel, Field

from studyrag.answering.prompts import load_prompt
from studyrag.config import CHAT_MODEL
from studyrag.observability import get_openai_client


class ChairLookupIntent(BaseModel):
    plausibly_chair_answerable: bool = Field(description="True only if a chair's own website could plausibly answer this.")
    reason: str = Field(description="One short sentence.")


def classify_chair_intent(question: str, client: OpenAI | None = None, model: str = CHAT_MODEL) -> ChairLookupIntent:
    client = client or get_openai_client()
    response = client.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": load_prompt("chair_classifier_prompt")},
            {"role": "user", "content": question},
        ],
        response_format=ChairLookupIntent,
    )
    return response.choices[0].message.parsed
