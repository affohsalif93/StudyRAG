"""Reciprocal Rank Fusion is pure, deterministic logic, tested
independent of whether hybrid search itself helped on this project's
eval set (it didn't).
"""

from __future__ import annotations

from studyrag.retrieval.hybrid import reciprocal_rank_fusion


def test_item_ranked_well_in_both_lists_wins():
    fused = reciprocal_rank_fusion(["A", "B", "C"], ["A", "C", "B"])
    assert fused[0][0] == "A"  # rank 1 in both


def test_item_missing_from_one_list_still_contributes():
    fused = reciprocal_rank_fusion(["A", "B"], ["C"])
    ids = [doc_id for doc_id, _ in fused]
    assert set(ids) == {"A", "B", "C"}


def test_higher_overall_rank_beats_lower():
    # X: rank 1 + rank 1; Y: rank 5 + rank 5 -- X must win decisively
    fused = reciprocal_rank_fusion(
        ["X", "p2", "p3", "p4", "Y"],
        ["X", "q2", "q3", "q4", "Y"],
    )
    scores = dict(fused)
    assert scores["X"] > scores["Y"]
