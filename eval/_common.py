"""Shared scoring logic for eval/run.py (bare pipeline) and
eval/run_langchain.py — same questions, same checks, so the two
baselines are directly comparable.
"""

from __future__ import annotations


def is_hit(question: dict, sources: list[dict]) -> bool:
    """Rule-shaped questions match on (source_id, paragraph, absatz);
    module-shaped questions match on (source_id, module_id) instead —
    module chunks have no paragraph/absatz at all.
    """
    expected_source = question.get("expected_source_id")
    if expected_source is None:
        return True  # unanswerable questions have no expected source to find

    expected_module_id = question.get("expected_module_id")
    for s in sources:
        if s.get("source_id") != expected_source:
            continue
        if expected_module_id is not None:
            if s.get("module_id") == expected_module_id:
                return True
            continue
        if question.get("expected_paragraph") and s.get("paragraph") != question["expected_paragraph"]:
            continue
        if question.get("expected_absatz") and s.get("absatz") != question["expected_absatz"]:
            continue
        return True
    return False


def is_correct_proxy(question: dict, answer: str) -> bool:
    """Keyword proxy, now with an optional `forbidden_keywords` list — some
    questions (e.g. the Bachelor-thesis-duration version conflict) have a
    plausible-but-wrong answer that a naive keyword check alone can't
    catch; forbidding that wrong value's keyword closes that gap.
    """
    answer_lower = answer.lower()
    if any(kw.lower() in answer_lower for kw in question.get("forbidden_keywords", [])):
        return False
    return any(kw.lower() in answer_lower for kw in question["expected_keywords"])
