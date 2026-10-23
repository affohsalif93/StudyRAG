"""Runs the same eval/questions.json through the LangChain pipeline and
compares against the bare-pipeline baseline (eval/run.py) -- the
LangChain version should reproduce those scores.

Usage: python -m eval.run_langchain
"""

from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv

from eval._common import is_correct_proxy, is_hit
from studyrag.langchain_pipeline.chain import answer_question, build_answer_chain, build_rewrite_chain
from studyrag.langchain_pipeline.vectorstore import load_vectorstore

REPO_ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_PATH = Path(__file__).parent / "questions.json"
RESULTS_PATH = Path(__file__).parent / "results_latest_langchain.json"
PERSIST_DIR = REPO_ROOT / "data" / "processed" / "embeddings" / "langchain_chroma"


def run() -> None:
    load_dotenv(REPO_ROOT / ".env")
    questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))

    vectorstore = load_vectorstore(str(PERSIST_DIR))
    answer_chain = build_answer_chain()
    rewrite_chain = build_rewrite_chain()

    hits = 0
    correct = 0
    results = []
    for q in questions:
        result = answer_question(q["question"], vectorstore, answer_chain, rewrite_chain, k=5)
        hit = is_hit(q, result["sources"])
        correct_proxy = is_correct_proxy(q, result["answer"])
        hits += hit
        correct += correct_proxy
        results.append({**q, "hit": hit, "correct_proxy": correct_proxy, "answer": result["answer"]})

        print(f"[{q['id']}] {q['type']}")
        print(f"  Q: {q['question']}")
        print(f"  hit={hit}  correct_proxy={correct_proxy}  abstained={result['abstained']}")
        print(f"  A: {result['answer'][:300]}")
        print()

    n = len(questions)
    print(f"Hit rate: {hits}/{n} ({hits / n:.0%})")
    print(f"Correctness (keyword proxy, NOT a validated judge): {correct}/{n} ({correct / n:.0%})")

    RESULTS_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {RESULTS_PATH}")


if __name__ == "__main__":
    run()
