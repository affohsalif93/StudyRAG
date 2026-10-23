"""Compares the AI judge (eval/ai_judge_results.json) against
independent human grades (eval/human_grades.json) — raw agreement plus
Cohen's kappa, since raw % agreement alone looks deceptively high when
both graders mostly say "correct" on a working system.

Usage: python -m eval.measure_agreement
"""

from __future__ import annotations

import json
from pathlib import Path

AI_JUDGE_PATH = Path(__file__).parent / "ai_judge_results.json"
HUMAN_PATH = Path(__file__).parent / "human_grades.json"


def cohens_kappa(pairs: list[tuple[bool, bool]]) -> float:
    n = len(pairs)
    observed_agreement = sum(1 for a, b in pairs if a == b) / n

    p_ai_true = sum(1 for a, _ in pairs if a) / n
    p_human_true = sum(1 for _, b in pairs if b) / n
    chance_agreement = p_ai_true * p_human_true + (1 - p_ai_true) * (1 - p_human_true)

    if chance_agreement == 1.0:
        return 1.0  # both graders always agreed on the same single label — no variance to correct for
    return (observed_agreement - chance_agreement) / (1 - chance_agreement)


def run() -> None:
    if not AI_JUDGE_PATH.exists():
        print(f"Missing {AI_JUDGE_PATH} — run `python -m eval.run_ai_judge` first.")
        return
    if not HUMAN_PATH.exists():
        print(f"Missing {HUMAN_PATH} — run `python -m eval.grade_human` yourself first.")
        return

    ai_results = {r["id"]: r for r in json.loads(AI_JUDGE_PATH.read_text(encoding="utf-8"))}
    human_results = {r["id"]: r for r in json.loads(HUMAN_PATH.read_text(encoding="utf-8"))}

    common_ids = sorted(set(ai_results) & set(human_results))
    missing = sorted(set(ai_results) - set(human_results))
    if missing:
        print(f"Note: {len(missing)} question(s) not yet human-graded, excluded from this comparison: {missing}")

    pairs = []
    disagreements = []
    for qid in common_ids:
        ai_correct = ai_results[qid]["ai_judge_correct"]
        human_correct = human_results[qid]["human_correct"]
        pairs.append((ai_correct, human_correct))
        if ai_correct != human_correct:
            disagreements.append(qid)

    n = len(pairs)
    if n == 0:
        print("No overlapping graded questions yet.")
        return

    agree = sum(1 for a, b in pairs if a == b)
    kappa = cohens_kappa(pairs)

    print(f"Compared on {n} questions.")
    print(f"Raw agreement: {agree}/{n} ({agree / n:.0%})")
    print(f"Cohen's kappa: {kappa:.2f}")
    print(
        "  (< 0: worse than chance, 0-0.2: slight, 0.2-0.4: fair, 0.4-0.6: moderate, "
        "0.6-0.8: substantial, 0.8-1.0: near-perfect)"
    )

    if disagreements:
        print(f"\nDisagreements ({len(disagreements)}):")
        for qid in disagreements:
            ai_r = ai_results[qid]
            human_r = human_results[qid]
            print(f"\n[{qid}] {ai_r['question']}")
            print(f"  AI judge:  correct={ai_r['ai_judge_correct']}  reason: {ai_r['ai_judge_reason']}")
            print(f"  Human:     correct={human_r['human_correct']}  note: {human_r.get('note') or '(none)'}")


if __name__ == "__main__":
    run()
