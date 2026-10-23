"""Grounded chat completion: query rewriting (skipped when there's no
history yet) + retrieval + one grounded answer call. Plain functions,
no classes — same style as the rest of studyrag.
"""

from __future__ import annotations

import sqlite3
from typing import Any

import numpy as np
from langsmith import traceable
from openai import OpenAI
from pydantic import BaseModel, Field

from studyrag.answering.prompts import load_prompt
from studyrag.answering.query_intent import classify_query_intent
from studyrag.answering.structured_lookup import classify_field_intent, format_field_value, lookup_module_fields
from studyrag.chair_lookup.agent import ask_chair_agent
from studyrag.chair_lookup.classifier import classify_chair_intent
from studyrag.config import (
    ABSTENTION_MESSAGE,
    ABSTENTION_THRESHOLD,
    DB_PATH,
    DEFAULT_USER_ID,
    ENABLE_CHAIR_LOOKUP,
    ENABLE_CHITCHAT,
    ENABLE_MEMORY,
    ENABLE_RERANKING,
    OFF_TOPIC_MESSAGE,
    RERANK_CANDIDATE_K,
    RETRIEVAL_MODE,
)
from studyrag.memory.classifier import classify_memory_intent
from studyrag.memory.store import SQLiteMemoryStore
from studyrag.memory.tools import load_memory, write_memory
from studyrag.observability import get_openai_client
from studyrag.retrieval.embed import retrieve
from studyrag.retrieval.hybrid import hybrid_retrieve
from studyrag.retrieval.rerank import rerank
from studyrag.trust.version_conflict import build_source_warning

CHAT_MODEL = "gpt-6-luna"  # confirmed against the live OpenAI model list, 2026-10-15

_memory_store = SQLiteMemoryStore()

DISCLAIMER = (
    "\n\n---\n*StudyRAG is a demonstration project, not official advice. "
    "Verify anything important with the examination office or the responsible chair.*"
)


class GroundedAnswer(BaseModel):
    answer: str = Field(description="The grounded answer, with [n] citations to the numbered passages.")
    abstained: bool = Field(description="True if the passages did not contain enough information to answer.")


def rewrite_query(
    question: str,
    history: list[dict],
    client: OpenAI | None = None,
    model: str = CHAT_MODEL,
) -> str:
    """Resolves references to prior turns ("its prerequisites") into a
    standalone question, using the conversation history. Skipped entirely
    (no API call) when there's no history yet — nothing to resolve.
    """
    if not history:
        return question

    client = client or get_openai_client()
    history_text = "\n".join(f"{turn['role']}: {turn['content']}" for turn in history)
    messages = [
        {"role": "system", "content": load_prompt("query_rewrite_prompt")},
        {"role": "user", "content": f"Conversation history:\n{history_text}\n\nNew question: {question}"},
    ]
    response = client.chat.completions.create(model=model, messages=messages)
    return response.choices[0].message.content.strip()


def _format_chunks(chunks: list[dict]) -> str:
    return "\n\n".join(f"[{i}] {c['text']}" for i, c in enumerate(chunks, start=1))


def _structured_fact_passage(
    question: str,
    top_chunk: dict,
    client: OpenAI,
    model: str,
    conn: sqlite3.Connection | None,
) -> dict | None:
    """CP, language, cycle, level, and duration are never embedded in any
    chunk's text, so no amount of retrieval can answer a question about
    them from text alone — resolved deterministically from the database
    instead. Returns an extra high-confidence passage injected alongside
    the normally retrieved ones (rather than short-circuiting the
    pipeline, which previously dropped the other half of a compound
    question like "how many CP ... and what are its prerequisites").
    Returns None whenever this isn't a structured-field question, or
    the database doesn't have the field either.
    """
    if top_chunk.get("kind") != "module":
        return None

    intent = classify_field_intent(question, top_chunk["title"], client=client, model=model)
    if not intent.is_structured_field_question or not intent.fields:
        return None

    conn = conn or sqlite3.connect(DB_PATH)
    row = lookup_module_fields(conn, top_chunk["module_row_id"], intent.fields)
    if row is None:
        return None

    resolved_facts = {f: format_field_value(f, row[f]) for f in intent.fields}
    resolved_facts = {f: v for f, v in resolved_facts.items() if v is not None}
    if not resolved_facts:
        return None  # the DB doesn't have it either — let the normal pipeline decline as usual

    facts_text = "; ".join(f"{field} = {value}" for field, value in resolved_facts.items())
    return {
        "kind": "module_field_lookup",
        "title": row["title"],
        "source_id": row["source_id"],
        "page_start": row["page_start"],
        "page_end": row["page_end"],
        "module_row_id": top_chunk["module_row_id"],
        "module_id": top_chunk["module_id"],
        "fields_used": list(resolved_facts.keys()),
        "score": 1.0,  # a verified DB fact, not a fuzzy match — never the reason to abstain
        "text": f"{row['title']} — database record: {facts_text}.",
    }


def _try_chair_lookup(question: str, client: OpenAI, user_id: str) -> str | None:
    """Fallback for when the core pipeline abstains — chair info
    (offering history, current contacts, thesis topics) is dynamic and
    chair-specific, never going to be in the static indexed corpus.
    Gated by a classifier first so the agent (several tool calls, real
    web fetches) is never attempted for things no chair page could
    plausibly answer either. Returns None (fall through to the normal
    abstention message) when the classifier says no, or when chair
    lookup is disabled entirely.
    """
    if not ENABLE_CHAIR_LOOKUP:
        return None
    intent = classify_chair_intent(question, client=client)
    if not intent.plausibly_chair_answerable:
        return None
    return ask_chair_agent(question, user_id=user_id)


def _maybe_remember(question: str, user_id: str, existing_facts: dict[str, str], client: OpenAI, model: str) -> None:
    """The core pipeline isn't a tool-calling agent, so it can't let the
    model decide mid-answer whether to call a `remember` tool — instead,
    a cheap classifier runs after every question (same
    classify-then-deterministic-write shape as structured_lookup and
    chair_lookup), and only its structured output ever reaches the
    actual write.
    """
    intent = classify_memory_intent(question, existing_facts, client=client, model=model)
    if not intent.should_remember:
        return
    for fact in intent.facts:
        write_memory(_memory_store, user_id, fact.key, fact.value)


@traceable(name="answer_question", run_type="chain")
def answer_question(
    question: str,
    vectors: np.ndarray,
    metadata: list[dict],
    history: list[dict] | None = None,
    k: int = 5,
    client: OpenAI | None = None,
    model: str = CHAT_MODEL,
    conn: sqlite3.Connection | None = None,
    retrieval_mode: str | None = None,
    user_id: str = DEFAULT_USER_ID,
    source_filter: dict[str, Any] | None = None,
) -> dict:
    """Thin wrapper around `_answer_question_impl`: injects known
    long-term memory into the generation call, then (if anything new was
    revealed) writes it back — kept as a wrapper, not inlined, so the
    core retrieval/generation logic stays the single, auditable thing it
    already was, with memory as a clearly separate concern around it.

    `source_filter`, e.g. `{"source_id": "po_master_2023"}` or
    `{"doc_type": ["po", "uepo"]}`, narrows retrieval to matching
    chunks before ranking — see retrieval/filters.py.
    """
    client = client or get_openai_client()
    memory_facts = load_memory(_memory_store, user_id) if ENABLE_MEMORY else {}

    result = _answer_question_impl(
        question, vectors, metadata, memory_facts, history, k, client, model, conn, retrieval_mode, user_id, source_filter
    )

    if ENABLE_MEMORY:
        _maybe_remember(question, user_id, memory_facts, client, model)

    return result


def _answer_question_impl(
    question: str,
    vectors: np.ndarray,
    metadata: list[dict],
    memory_facts: dict[str, str],
    history: list[dict] | None = None,
    k: int = 5,
    client: OpenAI | None = None,
    model: str = CHAT_MODEL,
    conn: sqlite3.Connection | None = None,
    retrieval_mode: str | None = None,
    user_id: str = DEFAULT_USER_ID,
    source_filter: dict[str, Any] | None = None,
) -> dict:
    """Retrieval is always based on a standalone version of `question` (the
    original if there's no history, the rewritten one otherwise) — the
    model never sees a question without also seeing what was retrieved
    for it. Returns the answer plus the exact sources it was given, so a
    caller can check citations against real chunks, not just trust the
    model's claim.

    `retrieval_mode` ("vector" or "hybrid") defaults to
    config.RETRIEVAL_MODE ("vector" — hybrid measurably regressed this
    project's eval set) but can be overridden per call, e.g. to re-test
    hybrid search after retuning it.
    """
    client = client or get_openai_client()
    conn = conn or sqlite3.connect(DB_PATH)
    history = history or []
    retrieval_mode = retrieval_mode or RETRIEVAL_MODE

    standalone_question = rewrite_query(question, history, client=client, model=model)
    # "score" means cosine similarity either way, so the abstention
    # threshold below is unaffected by which mode is used — only which
    # chunks get selected and in what order changes.
    candidate_k = RERANK_CANDIDATE_K if ENABLE_RERANKING else k
    if retrieval_mode == "hybrid":
        chunks = hybrid_retrieve(standalone_question, vectors, metadata, conn, k=candidate_k, client=client, filter=source_filter)
    else:
        chunks = retrieve(standalone_question, vectors, metadata, k=candidate_k, client=client, filter=source_filter)

    if ENABLE_RERANKING:
        # Fetch a larger pool cheaply, reorder with the same LLM used
        # elsewhere in this project, keep the real k. Reuses each
        # chunk's own cosine score unchanged — only selection/order
        # changes, so the abstention gate below still means what it
        # always meant.
        chunks = rerank(standalone_question, chunks, k=k, client=client, model=model)

    if chunks:
        fact_passage = _structured_fact_passage(question, chunks[0], client, model, conn)
        if fact_passage is not None:
            chunks = [fact_passage] + chunks  # cited as [1]: highest-confidence, goes first

    if not chunks or chunks[0]["score"] < ABSTENTION_THRESHOLD:
        # A deterministic safety net, not reliant on the model noticing
        # weak retrieval on its own — skips the LLM call entirely when
        # the best match isn't even plausible.
        if ENABLE_CHITCHAT:
            # A greeting retrieves nothing relevant too, so it lands right
            # here — without this, it got the same cold ABSTENTION_MESSAGE
            # as a genuine unanswerable question. Only runs inside this
            # already-weak-retrieval branch, so it costs nothing on the
            # normal, confidently-retrieved case.
            intent = classify_query_intent(standalone_question, client=client, model=model)
            if intent.category == "chitchat":
                return {
                    "question": question,
                    "standalone_question": standalone_question,
                    "answer": intent.reply + DISCLAIMER,
                    "sources": [],
                    "abstained": False,
                }
            if intent.category == "off_topic":
                return {
                    "question": question,
                    "standalone_question": standalone_question,
                    "answer": OFF_TOPIC_MESSAGE + DISCLAIMER,
                    "sources": [],
                    "abstained": True,
                }
            # category == "on_topic": a genuine question the corpus just
            # doesn't cover — fall through to the existing chair-lookup /
            # ABSTENTION_MESSAGE flow unchanged.

        chair_answer = _try_chair_lookup(question, client, user_id)
        if chair_answer is not None:
            return {
                "question": question,
                "standalone_question": standalone_question,
                "answer": chair_answer + DISCLAIMER,
                "sources": [{"kind": "chair_lookup"}],
                "abstained": False,
            }
        return {
            "question": question,
            "standalone_question": standalone_question,
            "answer": ABSTENTION_MESSAGE + DISCLAIMER,
            "sources": chunks,
            "abstained": True,
        }

    messages = [{"role": "system", "content": load_prompt("system_prompt")}]
    if memory_facts:
        facts_block = "\n".join(f"- {k}: {v}" for k, v in memory_facts.items())
        messages.append({"role": "system", "content": f"Known facts about this student:\n{facts_block}"})
    messages.extend(history)
    passages_block = _format_chunks(chunks)
    source_warning = build_source_warning(chunks)  # deterministic, not left to the model to notice
    if source_warning:
        passages_block = f"{source_warning}\n\n{passages_block}"
    messages.append(
        {
            "role": "user",
            "content": f"Passages:\n\n{passages_block}\n\nQuestion: {question}",
        }
    )

    # Structured output (not plain text) so the model's own "I don't
    # know" is a real, checkable signal — not just prose we'd have to
    # guess at from wording. Needed for the chair-lookup fallback below:
    # many chair-answerable questions still retrieve a superficially
    # related chunk that passes the score gate above, so the model
    # abstaining in its own answer is the only signal available; found
    # by running exactly this case for real, not assumed.
    response = client.chat.completions.parse(model=model, messages=messages, response_format=GroundedAnswer)
    parsed = response.choices[0].message.parsed

    if parsed.abstained:
        chair_answer = _try_chair_lookup(question, client, user_id)
        if chair_answer is not None:
            return {
                "question": question,
                "standalone_question": standalone_question,
                "answer": chair_answer + DISCLAIMER,
                "sources": [{"kind": "chair_lookup"}],
                "abstained": False,
            }

    return {
        "question": question,
        "standalone_question": standalone_question,
        "answer": parsed.answer + DISCLAIMER,
        "sources": chunks,
        "abstained": parsed.abstained,
    }
