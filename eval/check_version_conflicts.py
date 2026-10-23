"""Runs every eval question, flags which ones retrieved passages from
multiple documents, and asks the LLM judge whether any genuine conflict
was handled correctly (shown explicitly, not silently picked or
false-merged).

A "true conflict" verdict is only trustworthy if the citations it rests
on are accurate -- the conflict checker alone trusts that each passage
was represented accurately, so cross-check every "true conflict"
against citation accuracy before reporting it as real.

Usage: python -m eval.check_version_conflicts
"""

from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv

from studyrag.answering.chat import answer_question
from studyrag.retrieval.embed import load_index
from studyrag.trust.citation_check import check_all_citations
from studyrag.trust.version_conflict import check_conflict_handling, detect_multi_source

REPO_ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_PATH = Path(__file__).parent / "questions.json"
INDEX_PATH = REPO_ROOT / "data" / "processed" / "embeddings" / "chunk_index.npz"


def run() -> None:
    load_dotenv(REPO_ROOT / ".env")
    questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    vectors, metadata = load_index(str(INDEX_PATH))

    for q in questions:
        result = answer_question(q["question"], vectors, metadata, k=5)
        if result.get("abstained"):
            print(f"[{q['id']}] abstained — nothing to check")
            continue

        distinct_sources = detect_multi_source(result["sources"])
        if len(distinct_sources) < 2:
            print(f"[{q['id']}] single-document retrieval ({distinct_sources[0] if distinct_sources else 'none'}) — no conflict possible")
            continue

        judgement = check_conflict_handling(result["answer"], result["sources"])
        print(
            f"[{q['id']}] multi-document ({', '.join(distinct_sources)}) — "
            f"is_true_conflict={judgement.is_true_conflict} handled_correctly={judgement.handled_correctly}"
        )
        print(f"       reason: {judgement.reason}")

        if judgement.is_true_conflict:
            # Cross-check: a "conflict" is only real if the citations it
            # rests on are themselves accurate — don't trust it blindly.
            citation_checks = check_all_citations(result["answer"], result["sources"])
            failing = [c for c in citation_checks if not c["llm_judge"]["supported"]]
            if failing:
                print(
                    f"       CROSS-CHECK FAILED: {len(failing)} of the answer's citations don't actually "
                    f"support their claim — this 'conflict' may be fabricated, not real. "
                    f"Failing citation(s): {[c['citation'] for c in failing]}"
                )
            else:
                print("       cross-check passed: all citations in this answer are accurate.")


if __name__ == "__main__":
    run()
