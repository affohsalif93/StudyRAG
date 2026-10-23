"""Document-level metadata filters are pure, deterministic logic,
tested independent of the retrieval/generation pipeline that uses them.
"""

from __future__ import annotations

from studyrag.retrieval.filters import filter_indices, matches_filter


def test_matches_filter_single_value():
    chunk = {"source_id": "po_bachelor_2022", "doc_type": "po"}
    assert matches_filter(chunk, {"source_id": "po_bachelor_2022"})
    assert not matches_filter(chunk, {"source_id": "uepo_2026_109_de"})


def test_matches_filter_list_means_any_of():
    chunk = {"doc_type": "uepo"}
    assert matches_filter(chunk, {"doc_type": ["po", "uepo"]})
    assert not matches_filter(chunk, {"doc_type": ["po", "module_handbook"]})


def test_matches_filter_multiple_keys_all_must_match():
    chunk = {"doc_type": "po", "language": "de"}
    assert matches_filter(chunk, {"doc_type": "po", "language": "de"})
    assert not matches_filter(chunk, {"doc_type": "po", "language": "en"})


def test_matches_filter_missing_key_never_matches():
    chunk = {"doc_type": "po"}
    assert not matches_filter(chunk, {"language": "de"})


def test_filter_indices_returns_none_for_no_filter():
    metadata = [{"doc_type": "po"}, {"doc_type": "handbook"}]
    assert filter_indices(metadata, None) is None
    assert filter_indices(metadata, {}) is None


def test_filter_indices_returns_matching_positions_only():
    metadata = [
        {"doc_type": "po"},
        {"doc_type": "handbook"},
        {"doc_type": "uepo"},
    ]
    assert filter_indices(metadata, {"doc_type": ["po", "uepo"]}) == [0, 2]


def test_filter_indices_empty_when_nothing_matches():
    metadata = [{"doc_type": "handbook"}]
    assert filter_indices(metadata, {"doc_type": "po"}) == []
