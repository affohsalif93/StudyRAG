"""Retriever + a structured-output answer chain, built with LCEL
(prompt | model), plus usage logging. Parallel to
src/studyrag/answering/chat.py -- same job, LangChain components
instead of raw OpenAI SDK calls and a NumPy array.
"""

from __future__ import annotations

import sqlite3
import time
from typing import Any

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from openai import OpenAI
from pydantic import BaseModel, Field

from studyrag.answering.prompts import load_prompt
from studyrag.answering.structured_lookup import classify_field_intent, format_field_value, lookup_module_fields
from studyrag.config import (
    ABSTENTION_MESSAGE,
    ABSTENTION_THRESHOLD,
    CHAT_MODEL,
    DB_PATH,
    ENABLE_RERANKING,
    RERANK_CANDIDATE_K,
    RETRIEVAL_K,
)
from studyrag.observability import get_openai_client
from studyrag.retrieval.rerank import rerank
from studyrag.trust.version_conflict import build_source_warning

# gpt-6-luna doesn't accept a custom temperature (only the default, 1, is
# supported) — found by actually running this against the real API. The
# bare pipeline never hit this since it never set temperature either.

DISCLAIMER = (
    "\n\n---\n*StudyRAG is a demonstration project, not official advice. "
    "Verify anything important with the examination office or the responsible chair.*"
)


class AnswerWithSources(BaseModel):
    answer: str = Field(description="The grounded answer, with [n] citations to the numbered passages.")
    sources_used: list[int] = Field(description="Which numbered passages (1-based) were actually used.")
    abstained: bool = Field(description="True if the passages did not contain enough information to answer.")


def build_rewrite_chain():
    llm = ChatOpenAI(model=CHAT_MODEL)
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", load_prompt("query_rewrite_prompt")),
            ("human", "Conversation history:\n{history}\n\nNew question: {question}"),
        ]
    )
    return prompt | llm | StrOutputParser()


def build_answer_chain():
    llm = ChatOpenAI(model=CHAT_MODEL)
    structured_llm = llm.with_structured_output(AnswerWithSources, include_raw=True)
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", load_prompt("system_prompt")),
            ("human", "Passages:\n\n{passages}\n\nQuestion: {question}"),
        ]
    )
    return prompt | structured_llm


def _to_chroma_where(filter: dict[str, Any] | None) -> dict | None:
    """Translates the project's shared filter shape (plain value = exact
    match, list = any-of) into Chroma's own `where` clause syntax -- a
    list needs the explicit `$in` operator; Chroma rejects a bare list.
    """
    if not filter:
        return None
    return {key: ({"$in": list(value)} if isinstance(value, (list, tuple, set)) else value) for key, value in filter.items()}


def _format_docs(docs) -> str:
    return "\n\n".join(f"[{i}] {d.page_content}" for i, d in enumerate(docs, start=1))


def _structured_fact_document(
    question: str,
    top_doc,
    client: OpenAI,
    conn: sqlite3.Connection | None,
) -> Document | None:
    """Mirrors src/studyrag/answering/chat.py's bare pipeline: CP,
    language, cycle, level, and duration are never embedded in any
    chunk's text -- resolved deterministically from the database
    instead. Returns an extra high-confidence Document prepended to the
    normally retrieved ones (rather than short-circuiting the pipeline,
    which previously dropped the other half of a compound question like
    "how many CP ... and what are its prerequisites"). Returns None
    whenever this isn't a structured-field question, or the DB doesn't
    have the field either.
    """
    metadata = top_doc.metadata
    if metadata.get("kind") != "module":
        return None

    intent = classify_field_intent(question, metadata["title"], client=client, model=CHAT_MODEL)
    if not intent.is_structured_field_question or not intent.fields:
        return None

    conn = conn or sqlite3.connect(DB_PATH)
    row = lookup_module_fields(conn, metadata["module_row_id"], intent.fields)
    if row is None:
        return None

    resolved_facts = {f: format_field_value(f, row[f]) for f in intent.fields}
    resolved_facts = {f: v for f, v in resolved_facts.items() if v is not None}
    if not resolved_facts:
        return None

    facts_text = "; ".join(f"{field} = {value}" for field, value in resolved_facts.items())
    source_metadata = {
        "kind": "module_field_lookup",
        "title": row["title"],
        "source_id": row["source_id"],
        "page_start": row["page_start"],
        "page_end": row["page_end"],
        "module_row_id": metadata["module_row_id"],
        "module_id": metadata["module_id"],
        "fields_used": list(resolved_facts.keys()),
    }
    return Document(page_content=f"{row['title']} — database record: {facts_text}.", metadata=source_metadata)


def answer_question(
    question: str,
    vectorstore: Chroma,
    answer_chain,
    rewrite_chain=None,
    history: list[dict] | None = None,
    k: int = RETRIEVAL_K,
    conn: sqlite3.Connection | None = None,
    source_filter: dict[str, Any] | None = None,
) -> dict:
    history = history or []
    t0 = time.monotonic()

    if history and rewrite_chain is not None:
        history_text = "\n".join(f"{turn['role']}: {turn['content']}" for turn in history)
        standalone_question = rewrite_chain.invoke({"history": history_text, "question": question}).strip()
    else:
        standalone_question = question
    t_rewrite = time.monotonic()

    # similarity_search_with_score, not as_retriever().invoke() — the
    # retriever interface drops scores, and the abstention check needs
    # them. Chroma returns L2 distance (lower = better), not cosine
    # similarity (higher = better) — converted via similarity =
    # 1 - distance/2, valid because embeddings are unit vectors.
    candidate_k = RERANK_CANDIDATE_K if ENABLE_RERANKING else k
    docs_with_distance = vectorstore.similarity_search_with_score(
        standalone_question, k=candidate_k, filter=_to_chroma_where(source_filter)
    )
    # (doc, similarity) pairs, reranked together so each doc stays paired
    # with its own real cosine similarity — never a new LLM-derived score.
    pairs = [(doc, 1 - distance / 2) for doc, distance in docs_with_distance]

    if ENABLE_RERANKING:
        # Fetch a larger pool cheaply, reorder with the same LLM used
        # elsewhere in this project, keep the real k.
        pairs = rerank(standalone_question, pairs, k=k, get_text=lambda pair: pair[0].page_content)

    docs = [doc for doc, _ in pairs]
    top_similarity = pairs[0][1] if pairs else -1.0
    t_retrieve = time.monotonic()

    if docs:
        fact_doc = _structured_fact_document(question, docs[0], get_openai_client(), conn)
        if fact_doc is not None:
            docs = [fact_doc] + docs  # cited as [1]: highest-confidence, goes first
            top_similarity = 1.0  # a verified DB fact, not a fuzzy match — never the reason to abstain

    if top_similarity < ABSTENTION_THRESHOLD:
        # Same deterministic safety net as the bare pipeline — skip the
        # LLM call when the best match isn't plausible.
        print(f"[usage] rewrite={t_rewrite - t0:.2f}s retrieve={t_retrieve - t_rewrite:.2f}s abstained (score={top_similarity:.3f})")
        return {
            "question": question,
            "standalone_question": standalone_question,
            "answer": ABSTENTION_MESSAGE + DISCLAIMER,
            "abstained": True,
            "sources": [doc.metadata for doc in docs],
            "usage": {},
        }

    passages_block = _format_docs(docs)
    source_warning = build_source_warning([doc.metadata for doc in docs])
    if source_warning:
        passages_block = f"{source_warning}\n\n{passages_block}"

    result = answer_chain.invoke({"passages": passages_block, "question": question})
    parsed: AnswerWithSources = result["parsed"]
    usage = result["raw"].usage_metadata or {}
    t_generate = time.monotonic()

    print(
        f"[usage] rewrite={t_rewrite - t0:.2f}s retrieve={t_retrieve - t_rewrite:.2f}s "
        f"generate={t_generate - t_retrieve:.2f}s tokens_in={usage.get('input_tokens')} "
        f"tokens_out={usage.get('output_tokens')}"
    )

    return {
        "question": question,
        "standalone_question": standalone_question,
        "answer": parsed.answer + DISCLAIMER,
        "abstained": parsed.abstained,
        "sources": [doc.metadata for doc in docs],
        "usage": usage,
    }
