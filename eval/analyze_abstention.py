"""Records top retrieval scores for answerable vs. unanswerable
questions, plots them, and suggests an abstention threshold.

eval/questions.json currently has only 1 unanswerable question out of
6 -- not enough to pick a statistically sound threshold yet. This gives
the mechanism, ready to re-run as more unanswerable questions are added.

Usage: python -m eval.analyze_abstention
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # no display needed, just save a file
import matplotlib.pyplot as plt
from dotenv import load_dotenv

from studyrag.retrieval.embed import load_index, retrieve

REPO_ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_PATH = Path(__file__).parent / "questions.json"
INDEX_PATH = REPO_ROOT / "data" / "processed" / "embeddings" / "chunk_index.npz"
PLOT_PATH = Path(__file__).parent / "abstention_scores.png"


def collect_scores() -> list[dict]:
    load_dotenv(REPO_ROOT / ".env")
    questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    vectors, metadata = load_index(str(INDEX_PATH))

    records = []
    for q in questions:
        top = retrieve(q["question"], vectors, metadata, k=1)[0]
        records.append(
            {
                "id": q["id"],
                "type": q["type"],
                "is_unanswerable": q["type"] == "unanswerable",
                "top_score": top["score"],
            }
        )
    return records


def plot_scores(records: list[dict]) -> None:
    answerable = [r["top_score"] for r in records if not r["is_unanswerable"]]
    unanswerable = [r["top_score"] for r in records if r["is_unanswerable"]]

    fig, ax = plt.subplots(figsize=(6, 2.5))
    ax.scatter(answerable, [1] * len(answerable), label="answerable", marker="o", s=80)
    ax.scatter(unanswerable, [1] * len(unanswerable), label="unanswerable", marker="x", s=80, color="red")
    ax.set_yticks([])
    ax.set_xlabel("top-1 retrieval score (cosine similarity)")
    ax.set_title("Retrieval score by question answerability")
    ax.legend()
    fig.tight_layout()
    fig.savefig(PLOT_PATH, dpi=120)
    print(f"Wrote {PLOT_PATH}")


def suggest_threshold(records: list[dict]) -> None:
    answerable = [r["top_score"] for r in records if not r["is_unanswerable"]]
    unanswerable = [r["top_score"] for r in records if r["is_unanswerable"]]

    print(f"Answerable top-1 scores:   {sorted(answerable)}")
    print(f"Unanswerable top-1 scores: {sorted(unanswerable)}")

    if len(unanswerable) < 3:
        print(
            f"\nOnly {len(unanswerable)} unanswerable question(s) in the set — "
            "not enough to pick a real threshold yet. Add more before trusting any cut."
        )

    if answerable and unanswerable and min(answerable) > max(unanswerable):
        threshold = (min(answerable) + max(unanswerable)) / 2
        print(f"\nClean separation found. Suggested threshold: {threshold:.3f}")
    elif answerable and unanswerable:
        print("\nNo clean separation — answerable and unanswerable scores overlap.")
        print("A single global threshold would misclassify some questions with the current data.")


def run() -> None:
    records = collect_scores()
    for r in records:
        print(f"[{r['id']}] {r['type']:<28} top_score={r['top_score']:.3f}")
    print()
    suggest_threshold(records)
    plot_scores(records)


if __name__ == "__main__":
    run()
