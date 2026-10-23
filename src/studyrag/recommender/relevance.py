"""Per-module relevance scoring for the "every module, sized by relevance
to your goal" visualization. Reuses the retrieval index already built
for RAG -- only one new embedding call per track, for the goal query.
"""

from __future__ import annotations

import numpy as np
from openai import OpenAI

from studyrag.recommender.tracks import load_track
from studyrag.retrieval.embed import embed_texts

# Real cosine similarities cluster in a narrow band (~0.1-0.5), so a
# bubble-size encoding needs stretching to show any contrast. GAMMA > 1
# pulls the long tail down further after min-max normalization.
RELEVANCE_GAMMA = 2.2


def build_module_embeddings(vectors: np.ndarray, metadata: list[dict]) -> dict[str, np.ndarray]:
    """Mean-pools chunk-level retrieval embeddings into one vector per
    module_id, using only "about the module" chunks (not prerequisite text).
    """
    by_module: dict[str, list[np.ndarray]] = {}
    for vec, m in zip(vectors, metadata):
        if m.get("kind") != "module" or m.get("field_group") == "prerequisites":
            continue
        by_module.setdefault(m["module_id"], []).append(vec)

    return {module_id: np.mean(vecs, axis=0) for module_id, vecs in by_module.items()}


def _goal_query_text(track: dict) -> str:
    """What this goal is about, to embed and compare against every
    module: title, skills, and every curated module's reason text.
    """
    parts = [track["title"]]
    parts += [s["skill"].replace("_", " ") for s in track.get("skills_weighted", [])]
    for layer in ("core", "complementary", "nice_to_have"):
        parts += [item["reason"] for item in track.get(layer, [])]
    return ". ".join(parts)


def score_relevance(
    track_id: str,
    module_embeddings: dict[str, np.ndarray],
    client: OpenAI | None = None,
) -> dict[str, dict[str, float]]:
    """Returns {module_id: {"relevance": 0..1, "raw_similarity": cosine}}
    for every module with an embedding -- `relevance` is raw cosine
    similarity min-max normalized across this catalog then gamma-curved
    (see RELEVANCE_GAMMA), ready to map directly onto a bubble radius.
    """
    track = load_track(track_id)
    query_vector = embed_texts([_goal_query_text(track)], client=client)[0]

    module_ids = list(module_embeddings.keys())
    matrix = np.stack([module_embeddings[m] for m in module_ids])

    dot = matrix @ query_vector
    norms = np.linalg.norm(matrix, axis=1) * np.linalg.norm(query_vector)
    raw = dot / norms

    lo, hi = raw.min(), raw.max()
    normalized = (raw - lo) / (hi - lo) if hi > lo else np.zeros_like(raw)
    relevance = normalized**RELEVANCE_GAMMA

    return {
        module_ids[i]: {"relevance": float(relevance[i]), "raw_similarity": float(raw[i])} for i in range(len(module_ids))
    }


# Module-to-module similarity sits in a tighter band than goal-query
# similarity, so a fixed top-K per module already gives real neighbors.
SIMILARITY_TOP_K = 3


def similarity_edges(module_embeddings: dict[str, np.ndarray], top_k: int = SIMILARITY_TOP_K) -> list[dict]:
    """Every module's top_k nearest neighbors by cosine similarity, as
    deduplicated undirected edges. Independent of any track.
    """
    module_ids = list(module_embeddings.keys())
    matrix = np.stack([module_embeddings[m] for m in module_ids])
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    normalized = matrix / norms
    sim = normalized @ normalized.T
    np.fill_diagonal(sim, -1)

    seen_pairs: set[tuple[str, str]] = set()
    edges: list[dict] = []
    for i, module_id in enumerate(module_ids):
        neighbor_indices = np.argsort(-sim[i])[:top_k]
        for j in neighbor_indices:
            pair = tuple(sorted((module_id, module_ids[j])))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            edges.append({"source": pair[0], "target": pair[1], "similarity": float(sim[i, j])})

    return edges
