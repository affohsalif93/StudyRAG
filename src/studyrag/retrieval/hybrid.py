"""Hybrid search — fuses BM25 keyword ranking (keyword_search.py) with
vector/cosine-similarity ranking (embed.py) via Reciprocal Rank Fusion
(RRF), rather than blending the two raw score scales directly. Cosine
similarity lives in [-1, 1]; BM25 is unbounded and corpus-dependent --
any direct blend would need an arbitrary normalization choice. RRF only
uses each ranker's rank position, so it's scale-free by construction.
"""

from __future__ import annotations

import sqlite3
from typing import Any

import numpy as np
from openai import OpenAI

from studyrag.retrieval.embed import EMBEDDING_MODEL, embed_texts
from studyrag.retrieval.filters import filter_indices
from studyrag.retrieval.keyword_search import keyword_search

# 60 is the standard default from the original RRF paper (Cormack et al.,
# 2009) — large enough that rank 1 vs. rank 2 in one ranker doesn't
# automatically dominate a chunk that the other ranker ranks lower.
_RRF_K = 60


def reciprocal_rank_fusion(*ranked_id_lists: list[str], rrf_k: int = _RRF_K) -> list[tuple[str, float]]:
    """Each list is ids best-first. Returns (id, fused_score) pairs
    sorted best-first; an id missing from one list simply gets no
    contribution from that ranker, not a penalty.
    """
    scores: dict[str, float] = {}
    for ranked_ids in ranked_id_lists:
        for rank, doc_id in enumerate(ranked_ids, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (rrf_k + rank)
    return sorted(scores.items(), key=lambda kv: -kv[1])


def hybrid_retrieve(
    question: str,
    vectors: np.ndarray,
    metadata: list[dict],
    conn: sqlite3.Connection,
    k: int = 5,
    vector_k: int = 20,
    keyword_k: int = 20,
    client: OpenAI | None = None,
    model: str = EMBEDDING_MODEL,
    filter: dict[str, Any] | None = None,
) -> list[dict]:
    """Drop-in alternative to embed.py's retrieve(): same return shape
    (each result is {**metadata, "score": cosine_similarity}), same
    "score" semantics (cosine similarity, not the RRF fusion score) --
    deliberately, so the existing abstention threshold (calibrated against
    cosine similarity) keeps working unchanged. Hybrid search changes
    which chunks get selected and in what order, not what "score" means.
    `filter` is applied to both the vector and keyword halves before
    fusion, same semantics as embed.py:retrieve.
    """
    query_vector = embed_texts([question], client=client, model=model)[0]
    dot_products = vectors @ query_vector
    norms = np.linalg.norm(vectors, axis=1) * np.linalg.norm(query_vector)
    similarities = dot_products / norms

    allowed = filter_indices(metadata, filter)
    allowed_set = set(allowed) if allowed is not None else None

    if allowed_set is not None:
        masked = np.full(similarities.shape, -np.inf, dtype=similarities.dtype)
        masked[allowed] = similarities[allowed]
        vector_candidates = masked
    else:
        vector_candidates = similarities
    vector_top_indices = [i for i in np.argsort(-vector_candidates)[:vector_k] if vector_candidates[i] != -np.inf]
    vector_ranked_ids = [metadata[i]["chunk_id"] for i in vector_top_indices]

    chunk_id_to_index = {m["chunk_id"]: i for i, m in enumerate(metadata)}

    keyword_results = keyword_search(conn, question, k=keyword_k)
    keyword_ranked_ids = [
        chunk_id
        for chunk_id, _ in keyword_results
        if allowed_set is None or chunk_id_to_index.get(chunk_id) in allowed_set
    ]

    fused = reciprocal_rank_fusion(vector_ranked_ids, keyword_ranked_ids)

    results = []
    for chunk_id, _fused_score in fused[:k]:
        i = chunk_id_to_index.get(chunk_id)
        if i is None:
            continue  # a chunk_id FTS knows about that isn't in this vector index build
        results.append({**metadata[i], "score": float(similarities[i])})
    return results
