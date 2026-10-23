"""Request/response shapes for the HTTP API, kept separate from app.py
so they're easy to reuse.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000, description="The student's question.")
    history: list[Turn] = Field(default_factory=list, description="Prior turns, oldest first, for follow-up questions.")
    user_id: str | None = Field(default=None, description="Defaults to the single-user default if omitted.")
    source_filter: dict[str, Any] | None = Field(
        default=None,
        description='Narrow retrieval to matching chunks, e.g. {"doc_type": ["po", "uepo"]} or {"source_id": "po_master_2023"}.',
    )


class AskResponse(BaseModel):
    question: str
    answer: str
    sources: list[dict]
    abstained: bool


class FeedbackRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1)
    sources: list[dict] = Field(default_factory=list)
    rating: Literal["up", "down"]
    comment: str | None = Field(default=None, max_length=2000)


class FeedbackResponse(BaseModel):
    id: int
