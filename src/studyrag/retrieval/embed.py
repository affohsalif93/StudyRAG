"""Embed chunks with OpenAI and store them as a plain NumPy array + a
parallel metadata file — no FAISS, no vector database. At our corpus
size (~1000 chunks) brute-force cosine similarity over a NumPy matrix is
simpler and already fast. Also implements retrieve(question, k).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from openai import OpenAI

from studyrag.observability import get_openai_client
from studyrag.retrieval.filters import filter_indices

EMBEDDING_MODEL = "text-embedding-3-small"
_BATCH_SIZE = 100  # one API call per batch, not one per chunk


def embed_texts(texts: list[str], client: OpenAI | None = None, model: str = EMBEDDING_MODEL) -> np.ndarray:
    """Calls the OpenAI embeddings API. Requires OPENAI_API_KEY in the
    environment (or passed via `client`); see .env.example.
    """
    client = client or get_openai_client()
    vectors: list[list[float]] = []
    for i in range(0, len(texts), _BATCH_SIZE):
        batch = texts[i : i + _BATCH_SIZE]
        response = client.embeddings.create(model=model, input=batch)
        vectors.extend(d.embedding for d in response.data)
    return np.array(vectors, dtype=np.float32)


def build_index(chunks: list[dict], out_path: str, client: OpenAI | None = None) -> None:
    """Embeds every chunk's `text` and writes two files:
    `out_path` (the vectors, as .npz) and the same path with a
    `.meta.json` suffix (chunk metadata, same order as the vectors).
    """
    texts = [c["text"] for c in chunks]
    vectors = embed_texts(texts, client=client)

    np.savez(out_path, vectors=vectors)
    meta_path = Path(out_path).with_suffix("").with_suffix(".meta.json")
    meta_path.write_text(json.dumps(chunks, ensure_ascii=False), encoding="utf-8")


def load_index(path: str) -> tuple[np.ndarray, list[dict]]:
    vectors = np.load(path)["vectors"]
    meta_path = Path(path).with_suffix("").with_suffix(".meta.json")
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    return vectors, metadata


def retrieve(
    question: str,
    vectors: np.ndarray,
    metadata: list[dict],
    k: int = 5,
    client: OpenAI | None = None,
    model: str = EMBEDDING_MODEL,
    filter: dict[str, Any] | None = None,
) -> list[dict]:
    """Embeds `question` with the same model, returns the top-k chunks by
    cosine similarity, each with a `score` field added. `filter`, e.g.
    `{"source_id": "po_master_2023"}` or `{"doc_type": ["po", "uepo"]}`,
    narrows the candidate pool before ranking -- a filtered-out chunk can
    never win a top-k slot no matter its similarity.
    """
    query_vector = embed_texts([question], client=client, model=model)[0]

    dot_products = vectors @ query_vector
    norms = np.linalg.norm(vectors, axis=1) * np.linalg.norm(query_vector)
    similarities = dot_products / norms

    allowed = filter_indices(metadata, filter)
    if allowed is not None:
        mask = np.full(similarities.shape, -np.inf, dtype=similarities.dtype)
        mask[allowed] = similarities[allowed]
        similarities = mask

    top_k_indices = np.argsort(-similarities)[:k]
    return [{**metadata[i], "score": float(similarities[i])} for i in top_k_indices if similarities[i] != -np.inf]
