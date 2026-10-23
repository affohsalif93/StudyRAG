"""Runs every eval question, then checks every citation the answer
actually used -- rule-based first, then the LLM judge -- and prints the
faithfulness/citation-accuracy table.

Usage: python -m eval.check_citations
"""

from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv

from studyrag.answering.chat import answer_question
from studyrag.retrieval.embed import load_index
from studyrag.trust.citation_check import check_all_citations

REPO_ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_PATH = Path(__file__).parent / "questions.json"
RESULTS_PATH = Path(__file__).parent / "citation_check_results.json"
INDEX_PATH = REPO_ROOT / "data" / "processed" / "embeddings" / "chunk_index.npz"


def run() -> None:
    load_dotenv(REPO_ROOT / ".env")
    questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    vectors, metadata = load_index(str(INDEX_PATH))

    all_checks = []
    for q in questions:
        result = answer_question(q["question"], vectors, metadata, k=5)
        if result.get("abstained"):
            print(f"[{q['id']}] abstained — no citations to check")
            continue

        checks = check_all_citations(result["answer"], result["sources"])
        if not checks:
            print(f"[{q['id']}] no citations found in the answer")
            continue

        for c in checks:
            c["question_id"] = q["id"]
            all_checks.append(c)
            if "error" in c:
                # A claim with no citation number, or a citation number
                # with no matching source — not a rule/judge verdict to
                # report, just a malformed citation in the answer itself.
                print(f"[{q['id']}] citation [{c.get('citation', '?')}]  ERROR: {c['error']}")
                continue
            rule_mark = "OK" if c["rule_based"]["passed"] else "FAIL"
            judge_mark = "OK" if c["llm_judge"]["supported"] else "FAIL"
            print(f"[{q['id']}] citation [{c['citation']}]  rule={rule_mark}  judge={judge_mark}")
            if rule_mark == "FAIL" or judge_mark == "FAIL":
                print(f"       sentence: {c['sentence']}")
                print(f"       judge reason: {c['llm_judge']['reason']}")

    scored_checks = [c for c in all_checks if "error" not in c]
    n = len(scored_checks)
    rule_pass = sum(1 for c in scored_checks if c["rule_based"]["passed"])
    judge_pass = sum(1 for c in scored_checks if c["llm_judge"]["supported"])
    n_errors = len(all_checks) - n
    if n_errors:
        print(f"\n{n_errors} malformed citation(s) excluded from the pass-rate denominators (see ERROR lines above).")

    print()
    print(f"Citations checked: {n}")
    print(f"Rule-based pass (numbers match):  {rule_pass}/{n} ({rule_pass / n:.0%})" if n else "No citations to check.")
    print(f"LLM-judge pass (faithfulness):    {judge_pass}/{n} ({judge_pass / n:.0%})" if n else "")

    RESULTS_PATH.write_text(json.dumps(all_checks, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {RESULTS_PATH}")


if __name__ == "__main__":
    run()
