"""The parts of relevance.py that don't call the OpenAI API are pure,
deterministic logic, unit-tested here. score_relevance() itself needs
a real embedding call and is exercised against real data instead.
"""

from __future__ import annotations

import numpy as np

from studyrag.recommender.relevance import _goal_query_text, build_module_embeddings, similarity_edges


def test_goal_query_text_includes_title_skills_and_reasons():
    track = {
        "title": "Software engineer",
        "skills_weighted": [{"skill": "software_design", "weight": None}],
        "core": [{"module_id": "1", "module": "A", "reason": "Reason A."}],
        "complementary": [{"module_id": "2", "module": "B", "reason": "Reason B."}],
        "nice_to_have": [],
    }
    text = _goal_query_text(track)
    assert "Software engineer" in text
    assert "software design" in text
    assert "Reason A." in text
    assert "Reason B." in text


def test_build_module_embeddings_averages_teaching_chunks_only():
    vectors = np.array(
        [
            [1.0, 0.0],
            [3.0, 0.0],
            [10.0, 10.0],  # prerequisites chunk -- must not pull the average
            [0.0, 1.0],  # a rule chunk -- must not be grouped as a module at all
        ],
        dtype=np.float32,
    )
    metadata = [
        {"kind": "module", "module_id": "m1", "field_group": "teaches"},
        {"kind": "module", "module_id": "m1", "field_group": None},
        {"kind": "module", "module_id": "m1", "field_group": "prerequisites"},
        {"kind": "rule", "module_id": "m1", "field_group": None},
    ]
    result = build_module_embeddings(vectors, metadata)
    assert list(result.keys()) == ["m1"]
    np.testing.assert_allclose(result["m1"], [2.0, 0.0])


def test_similarity_edges_dedupes_and_excludes_self():
    # a, b near-identical; c orthogonal to both -- top_k=1 should pair a<->b
    # once (not twice, even though each lists the other as its nearest
    # neighbor), and never link a module to itself.
    embeddings = {
        "a": np.array([1.0, 0.0]),
        "b": np.array([0.9, 0.1]),
        "c": np.array([0.0, 1.0]),
    }
    edges = similarity_edges(embeddings, top_k=1)
    pairs = {tuple(sorted((e["source"], e["target"]))) for e in edges}
    assert ("a", "b") in pairs
    assert len(edges) == len(pairs)  # no duplicate undirected edge
    assert all(e["source"] != e["target"] for e in edges)
