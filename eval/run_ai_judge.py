"""Runs the LLM correctness judge over the frozen answer set in
eval/results_latest.json, not by re-calling answer_question -- gpt-6-luna
only supports temperature=1, so re-generating would grade a different
set of answers than whatever the human grades next. Run eval/run.py
first for a fresh set of answers.

Usage: python -m eval.run_ai_judge
"""

from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from studyrag.trust.correctness_judge import judge_correctness

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_PATH = Path(__file__).parent / "results_latest.json"
OUT_PATH = Path(__file__).parent / "ai_judge_results.json"


def run() -> None:
    load_dotenv(REPO_ROOT / ".env")
    results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    client = OpenAI()

    judged = []
    agree_with_proxy = 0
    for r in results:
        judgement = judge_correctness(r["question"], r["answer"], r["sources"], client=client)
        matches_proxy = judgement.correct == r["correct_proxy"]
        agree_with_proxy += matches_proxy
        judged.append(
            {
                "id": r["id"],
                "question": r["question"],
                "answer": r["answer"],
                "keyword_proxy_correct": r["correct_proxy"],
                "ai_judge_correct": judgement.correct,
                "ai_judge_reason": judgement.reason,
            }
        )
        flag = "" if matches_proxy else "  <-- disagrees with keyword proxy"
        print(f"[{r['id']}] proxy={r['correct_proxy']}  ai_judge={judgement.correct}{flag}")
        print(f"       {judgement.reason}")

    n = len(judged)
    print(f"\nAI judge vs keyword proxy agreement: {agree_with_proxy}/{n} ({agree_with_proxy / n:.0%})")
    print("(This is NOT validation — it's just a sanity check against the proxy it's meant to replace.")
    print(" Real validation needs independent human grades: run eval/grade_human.py yourself, then")
    print(" eval/measure_agreement.py to compare the AI judge against your own judgement.)")

    OUT_PATH.write_text(json.dumps(judged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    run()
