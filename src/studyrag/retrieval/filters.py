"""Document-level metadata filters. The index already combines every
document (handbook + all regulations) into one store -- this lets a
caller narrow a query to a specific document, document type, or language
before similarity ranking even runs, rather than hoping the right
document wins on pure relevance.
"""

from __future__ import annotations

from typing import Any


def matches_filter(chunk_metadata: dict, filter: dict[str, Any]) -> bool:
    """Exact-match on every key in `filter`. A filter value can be a
    single value (`{"source_id": "po_master_2023"}`) or a list of
    allowed values (`{"doc_type": ["po", "uepo"]}`, meaning either).
    A chunk missing a filtered-on key never matches — never silently
    "passes" a filter it has no opinion on.
    """
    for key, expected in filter.items():
        actual = chunk_metadata.get(key)
        if isinstance(expected, (list, tuple, set)):
            if actual not in expected:
                return False
        elif actual != expected:
            return False
    return True


def filter_indices(metadata: list[dict], filter: dict[str, Any] | None) -> list[int] | None:
    """Returns the indices of `metadata` matching `filter`, or None if
    there's no filter at all (the common case — callers should treat
    None as "every index," not iterate an empty filter for no reason).
    """
    if not filter:
        return None
    return [i for i, m in enumerate(metadata) if matches_filter(m, filter)]
