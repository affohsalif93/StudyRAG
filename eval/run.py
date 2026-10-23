"""Evaluation runner: runs eval/questions.json through answer_question()
and computes hit rate and a crude keyword-based correctness proxy. Not
the validated AI judge (see eval/run_ai_judge.py) -- this is the
bare-pipeline baseline.

Usage: python -m eval.run
"""

from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv

from eval._common import is_correct_proxy, is_hit
from studyrag.answering.chat import answer_question
from studyrag.retrieval.embed import load_index

REPO_ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_PATH = Path(__file__).parent / "questions.json"
RESULTS_PATH = Path(__file__).parent / "results_latest.json"
INDEX_PATH = REPO_ROOT / "data" / "processed" / "embeddings" / "chunk_index.npz"


def run() -> None:
    load_dotenv(REPO_ROOT / ".env")
    questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    vectors, metadata = load_index(str(INDEX_PATH))

    hits = 0
    correct = 0
    results = []
    for q in questions:
        result = answer_question(q["question"], vectors, metadata, k=5)
        hit = is_hit(q, result["sources"])
        correct_proxy = is_correct_proxy(q, result["answer"])
        hits += hit
        correct += correct_proxy
        results.append(
            {**q, "hit": hit, "correct_proxy": correct_proxy, "answer": result["answer"], "sources": result["sources"]}
        )

        print(f"[{q['id']}] {q['type']}")
        print(f"  Q: {q['question']}")
        print(f"  hit={hit}  correct_proxy={correct_proxy}")
        print(f"  A: {result['answer'][:300]}")
        print()

    n = len(questions)
    print(f"Hit rate: {hits}/{n} ({hits / n:.0%})")
    print(f"Correctness (keyword proxy, NOT a validated judge): {correct}/{n} ({correct / n:.0%})")

    RESULTS_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {RESULTS_PATH}")


if __name__ == "__main__":
    run()
