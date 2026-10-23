"""You run this, not Claude -- validating the AI judge means comparing
it against independent human judgement. Walks through the same answers
the AI judge graded (eval/results_latest.json) and asks you to mark each
correct/incorrect, blind to the AI judge's verdict. Resumable:
already-graded ids are skipped.

Usage: python -m eval.grade_human
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_PATH = Path(__file__).parent / "results_latest.json"
OUT_PATH = Path(__file__).parent / "human_grades.json"


def run() -> None:
    results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    graded: dict[str, dict] = {}
    if OUT_PATH.exists():
        graded = {str(g["id"]): g for g in json.loads(OUT_PATH.read_text(encoding="utf-8"))}

    for r in results:
        key = str(r["id"])
        if key in graded:
            continue

        print(f"\n[{r['id']}] {r['type']}")
        print(f"Q: {r['question']}")
        print(f"A: {r['answer']}")
        while True:
            raw = input("Correct? [y/n/skip/quit]: ").strip().lower()
            if raw in ("y", "n", "skip", "quit"):
                break
            print("Please answer y, n, skip, or quit.")

        if raw == "quit":
            break
        if raw == "skip":
            continue

        note = input("Optional note (why / anything to flag): ").strip()
        graded[key] = {"id": r["id"], "human_correct": raw == "y", "note": note}
        OUT_PATH.write_text(
            json.dumps(sorted(graded.values(), key=lambda g: g["id"]), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    n_graded = len(graded)
    n_total = len(results)
    print(f"\nGraded {n_graded}/{n_total}. Progress saved to {OUT_PATH}.")
    if n_graded < n_total:
        print("Run again to continue where you left off.")
    else:
        print("All graded — run `python -m eval.measure_agreement` to compare against the AI judge.")


if __name__ == "__main__":
    run()
