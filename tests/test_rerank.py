"""rerank()'s index-sanitization logic is pure and deterministic --
never trust the model's returned indices blindly -- tested independent
of the LLM call itself.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from studyrag.retrieval.rerank import RerankResult, rerank


def test_returns_unchanged_when_candidates_fit_within_k():
    candidates = [{"text": "a"}, {"text": "b"}]
    assert rerank("q", candidates, k=5) == candidates


def _mock_client(top_indices):
    client = MagicMock()
    client.chat.completions.parse.return_value.choices = [MagicMock(message=MagicMock(parsed=RerankResult(top_indices=top_indices)))]
    return client


def test_reorders_by_returned_indices():
    candidates = [{"text": f"c{i}"} for i in range(1, 7)]
    client = _mock_client([3, 1, 5])
    result = rerank("q", candidates, k=3, client=client)
    assert [c["text"] for c in result] == ["c3", "c1", "c5"]


def test_ignores_out_of_range_and_duplicate_indices():
    candidates = [{"text": f"c{i}"} for i in range(1, 7)]
    client = _mock_client([3, 3, 99, 1])
    result = rerank("q", candidates, k=3, client=client)
    assert [c["text"] for c in result] == ["c3", "c1", "c2"]  # fills remaining slot from original order


def test_fills_remaining_slots_when_model_returns_too_few():
    candidates = [{"text": f"c{i}"} for i in range(1, 7)]
    client = _mock_client([5])
    result = rerank("q", candidates, k=3, client=client)
    assert [c["text"] for c in result] == ["c5", "c1", "c2"]
