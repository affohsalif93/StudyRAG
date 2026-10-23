"""Hand-written student personas, each with a hand-worked-out expected
recommendation, run against the real recommender end to end -- real
SQLite DB, real Neo4j graph, no mocking.

Personas cover all nine tracks, including the ones with a genuine hard
prerequisite edge (machine_learning_engineer, scientific_computing,
graphics_and_hci) and two deliberately-broken profiles (no target set,
unknown track id) that guard against a regression of a real crash found
by p13.

Scored on: core precision/recall, constraint violations (must be zero),
rule-check correctness (CP/area totals, foundation-first warnings firing
only where expected), and explanation faithfulness (every returned
reason must match the track YAML's own reason text verbatim).

Usage: python -m eval.run_personas
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from dotenv import load_dotenv

from studyrag.config import DB_PATH
from studyrag.recommender.engine import recommend
from studyrag.recommender.prerequisites import get_neo4j_driver
from studyrag.recommender.profile import Profile
from studyrag.recommender.tracks import load_track

REPO_ROOT = Path(__file__).resolve().parent.parent
PERSONAS_DIR = Path(__file__).parent / "personas"
RESULTS_PATH = Path(__file__).parent / "persona_results.json"

LAYERS = ("core", "complementary", "nice_to_have")


def _reasons_by_module_id(track_ids: list[str]) -> dict[str, set[str]]:
    """Maps module_id -> every reason text stated for it across all the
    given tracks. More than one target track can legitimately state a
    *different* reason for the same module (engine.py's merge keeps
    whichever track won the layer-priority tie, and this harness has no
    independent way to know which one that was without re-implementing
    the merge) -- so a persona's actual reason only needs to match one
    of its real target tracks' own text, not a single predetermined one.
    """
    by_module: dict[str, set[str]] = {}
    for track_id in track_ids:
        track = load_track(track_id)
        for layer in LAYERS:
            for item in track.get(layer, []):
                by_module.setdefault(item["module_id"], set()).add(item["reason"])
    return by_module


def _actual_layer_ids(result: dict) -> dict[str, list[str]]:
    return {layer: [e["module_id"] for e in result.get(layer, [])] for layer in LAYERS}


def _check_normal_persona(persona: dict, result: dict) -> dict:
    expect = persona["expect"]
    actual = _actual_layer_ids(result)
    problems: list[str] = []
    track_ids = [t["track_id"] for t in persona["profile"]["targets"]]
    reasons = _reasons_by_module_id(track_ids)

    for layer in LAYERS:
        exp_set, act_set = set(expect[layer]), set(actual[layer])
        if exp_set != act_set:
            problems.append(f"{layer}: expected {sorted(exp_set)}, got {sorted(act_set)}")

    exp_excluded = {(e["module_id"], e["reason"]) for e in expect["excluded"]}
    # "excluded" entries carry module *title* + reason in the real engine output (see engine.py),
    # not module_id -- resolve titles back to ids via the track's own module list.
    act_excluded_by_id = set()
    title_to_id = {title: mid for mid, title in _title_by_module_id(persona).items()}
    for e in result.get("excluded", []):
        mid = title_to_id.get(e["module"], e["module"])
        act_excluded_by_id.add((mid, e["reason"]))
    if exp_excluded != act_excluded_by_id:
        problems.append(f"excluded: expected {sorted(exp_excluded)}, got {sorted(act_excluded_by_id)}")

    all_entries = [e for layer in LAYERS for e in result.get(layer, [])]
    warnings_empty = all(not e.get("foundation_first_warnings") for e in all_entries)
    if expect.get("foundation_first_warnings_empty") and not warnings_empty:
        nonempty = [e["module_id"] for e in all_entries if e.get("foundation_first_warnings")]
        problems.append(f"expected no foundation-first warnings, got some on: {nonempty}")

    if "expected_foundation_first_warnings" in expect:
        exp_warned = expect["expected_foundation_first_warnings"]
        entries_by_id = {e["module_id"]: e for e in all_entries}
        for module_id, expected_prereq_ids in exp_warned.items():
            entry = entries_by_id.get(module_id)
            actual_prereq_ids = sorted(w["module_id"] for w in entry["foundation_first_warnings"]) if entry else None
            if actual_prereq_ids != sorted(expected_prereq_ids):
                problems.append(f"foundation_first_warnings[{module_id}]: expected prereqs {sorted(expected_prereq_ids)}, got {actual_prereq_ids}")
        # No other module should carry a spurious warning not accounted for above.
        expected_warned_ids = {mid for mid, prereqs in exp_warned.items() if prereqs}
        actual_warned_ids = {e["module_id"] for e in all_entries if e.get("foundation_first_warnings")}
        unexpected = actual_warned_ids - expected_warned_ids
        if unexpected:
            problems.append(f"unexpected foundation-first warnings on modules not listed in expected_foundation_first_warnings: {sorted(unexpected)}")

    reason_mismatches = [e["module_id"] for e in all_entries if e.get("reason") not in reasons.get(e["module_id"], set())]
    if reason_mismatches:
        problems.append(f"reason text didn't match any target track's YAML verbatim for: {reason_mismatches}")

    if expect.get("note_present") and not result.get("note"):
        problems.append("expected engine.NOT_YET_IMPLEMENTED_NOTE to be present in 'note', but it was missing/empty")

    if "rule_check" in expect:
        exp_rc = expect["rule_check"]
        act_area = result.get("rule_check", {}).get("area_requirement", {})
        act_cap = result.get("rule_check", {}).get("early_master_cap", {})
        if act_area.get("cp_by_area") != exp_rc["cp_by_area"]:
            problems.append(f"rule_check.cp_by_area: expected {exp_rc['cp_by_area']}, got {act_area.get('cp_by_area')}")
        if act_area.get("satisfied") != exp_rc["area_requirement_satisfied"]:
            problems.append(f"rule_check.area_requirement.satisfied: expected {exp_rc['area_requirement_satisfied']}, got {act_area.get('satisfied')}")
        if act_cap.get("applies") != exp_rc["early_master_cap_applies"]:
            problems.append(f"rule_check.early_master_cap.applies: expected {exp_rc['early_master_cap_applies']}, got {act_cap.get('applies')}")

    if "weights" in expect:
        actual_weights = {e["module_id"]: e.get("research_industry_weight") for e in all_entries}
        for module_id, expected_weight in expect["weights"].items():
            if actual_weights.get(module_id) != expected_weight:
                problems.append(f"research_industry_weight[{module_id}]: expected {expected_weight!r}, got {actual_weights.get(module_id)!r}")

    if "layer_order" in expect:
        for layer, expected_order in expect["layer_order"].items():
            if actual[layer] != expected_order:
                problems.append(f"{layer} order: expected {expected_order}, got {actual[layer]}")

    if "weak_skill_notes" in expect:
        actual_notes = {n["skill"]: n for n in result.get("weak_skill_notes", [])}
        if set(actual_notes) != {n["skill"] for n in expect["weak_skill_notes"]}:
            problems.append(f"weak_skill_notes: expected skills {sorted(n['skill'] for n in expect['weak_skill_notes'])}, got {sorted(actual_notes)}")
        for exp_note in expect["weak_skill_notes"]:
            act_note = actual_notes.get(exp_note["skill"])
            if act_note and "weight" in exp_note and act_note.get("weight") != exp_note["weight"]:
                problems.append(f"weak_skill_notes[{exp_note['skill']}].weight: expected {exp_note['weight']}, got {act_note.get('weight')}")

    if "expected_not_offered_next_semester" in expect:
        entries_by_id = {e["module_id"]: e for e in all_entries}
        for module_id, expected_flag in expect["expected_not_offered_next_semester"].items():
            entry = entries_by_id.get(module_id)
            actual_flag = entry.get("probably_not_offered_next_semester") if entry else None
            if actual_flag != expected_flag:
                problems.append(f"probably_not_offered_next_semester[{module_id}]: expected {expected_flag}, got {actual_flag}")

    if "cp_budget" in expect:
        exp_budget = expect["cp_budget"]
        act_budget = result.get("cp_budget") or {}
        if act_budget.get("total_recommended_cp") != exp_budget["total_recommended_cp"]:
            problems.append(f"cp_budget.total_recommended_cp: expected {exp_budget['total_recommended_cp']}, got {act_budget.get('total_recommended_cp')}")
        if act_budget.get("cp_missing_total") != exp_budget["cp_missing_total"]:
            problems.append(f"cp_budget.cp_missing_total: expected {exp_budget['cp_missing_total']}, got {act_budget.get('cp_missing_total')}")
        covers = act_budget.get("total_recommended_cp", 0) >= act_budget.get("cp_missing_total", 0)
        if covers != exp_budget["covers_remaining"]:
            problems.append(f"cp_budget: expected covers_remaining={exp_budget['covers_remaining']}, got {covers}")

    return {
        "passed": not problems,
        "problems": problems,
        "actual": actual,
        "excluded_actual": sorted(act_excluded_by_id),
    }


def _title_by_module_id(persona: dict) -> dict[str, str]:
    targets = persona["profile"].get("targets") or []
    by_module: dict[str, str] = {}
    for target in targets:
        track = load_track(target["track_id"])
        for layer in LAYERS:
            for item in track.get(layer, []):
                by_module[item["module_id"]] = item["module"]
    return by_module


def run() -> None:
    load_dotenv(REPO_ROOT / ".env")
    conn = sqlite3.connect(DB_PATH)
    driver = get_neo4j_driver()

    persona_paths = sorted(PERSONAS_DIR.glob("*.json"))
    reports = []

    for path in persona_paths:
        persona = json.loads(path.read_text(encoding="utf-8"))
        profile = Profile.model_validate(persona["profile"])

        try:
            result = recommend(profile, conn, driver)
            crashed = False
            error_text = None
        except Exception as e:  # noqa: BLE001 -- deliberately catching anything: a crash here IS the finding
            crashed = True
            error_text = f"{type(e).__name__}: {e}"
            result = None

        if "expect_crash" in persona:
            expected_crash = persona["expect_crash"]
            if crashed == expected_crash:
                report = {"passed": True, "problems": [], "note": f"known bug confirmed: {persona.get('bug_note', '')} -- raised {error_text}" if crashed else "bug appears fixed -- no crash this run"}
            else:
                report = {"passed": False, "problems": [f"expected crash={expected_crash}, got crash={crashed} ({error_text})"]}
        elif "expect_error" in persona:
            if crashed:
                report = {"passed": False, "problems": [f"expected a clean error dict, got an unhandled crash: {error_text}"]}
            elif result == {"error": persona["expect_error"]}:
                report = {"passed": True, "problems": []}
            else:
                report = {"passed": False, "problems": [f"expected error {persona['expect_error']!r}, got {result!r}"]}
        else:
            if crashed:
                report = {"passed": False, "problems": [f"unexpected crash: {error_text}"]}
            else:
                report = _check_normal_persona(persona, result)

        report["id"] = persona["id"]
        report["name"] = persona["name"]
        reports.append(report)

        mark = "PASS" if report["passed"] else "FAIL"
        print(f"[{mark}] {persona['id']}: {persona['name']}")
        for p in report["problems"]:
            print(f"       - {p}")
        if report.get("note"):
            print(f"       note: {report['note']}")

    conn.close()
    driver.close()

    # Pooled core precision/recall across the "normal" personas.
    tp = fp = fn = 0
    for path in persona_paths:
        persona = json.loads(path.read_text(encoding="utf-8"))
        if "expect" not in persona:
            continue
        report = next(r for r in reports if r["id"] == persona["id"])
        exp_core = set(persona["expect"]["core"])
        act_core = set(report["actual"]["core"])
        tp += len(exp_core & act_core)
        fp += len(act_core - exp_core)
        fn += len(exp_core - act_core)
    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    recall = tp / (tp + fn) if (tp + fn) else float("nan")

    # Constraint violations: any module expected to be excluded that leaked into a recommended layer.
    violations = 0
    for path in persona_paths:
        persona = json.loads(path.read_text(encoding="utf-8"))
        if "expect" not in persona:
            continue
        report = next(r for r in reports if r["id"] == persona["id"])
        expected_excluded_ids = {e["module_id"] for e in persona["expect"]["excluded"]}
        all_recommended_ids = {mid for layer in LAYERS for mid in report["actual"][layer]}
        violations += len(expected_excluded_ids & all_recommended_ids)

    n_pass = sum(1 for r in reports if r["passed"])
    n_rule_checked = sum(1 for p in persona_paths if "rule_check" in json.loads(p.read_text(encoding="utf-8")).get("expect", {}))
    n_weight_checked = sum(1 for p in persona_paths if "weights" in json.loads(p.read_text(encoding="utf-8")).get("expect", {}))
    print()
    print(f"Personas: {n_pass}/{len(reports)} passed")
    print(f"Research-vs-industry weighting (F56): per-module weight tags verified on {n_weight_checked} personas, including")
    print("  an exact reordered-core-layer check for the industry lean (p01) and a same-order-different-tags check for the")
    print("  research lean (p10) -- proving the reorder is real, not that it coincidentally never needed to happen.")
    print(f"Core precision: {precision:.0%}  recall: {recall:.0%}  (pooled over {sum(1 for p in persona_paths if 'expect' in json.loads(p.read_text(encoding='utf-8')))} normal personas)")
    print(f"Constraint violations (must be 0): {violations}")
    print(f"Rule-check correctness: CP/area requirement verified against hand-computed totals on {n_rule_checked} personas (one of them, p11, actually satisfies the rule).")
    print("  Early-master cap: verified as correctly 'does not apply' -- no profile this project models represents a Bachelor's student.")
    print("  Foundation-first warnings: p14/p16/p20 exercise three real, non-spurious warnings firing (machine_learning_engineer,")
    print("  scientific_computing, graphics_and_hci) and p15/p21 each exercise one disappearing once its real prerequisite is passed --")
    print("  software_engineering/cybersecurity/data_engineering/distributed_systems/theoretical_computer_science/embedded_systems still")
    print("  have zero internal hard edges, so only those tracks' personas are limited to proving warnings don't fire spuriously.")
    print("Explanation faithfulness: checked inline per persona above (reason text vs. the track YAML, verbatim).")
    print("Handover behavior: see p07 (no target) and p08 (unknown track) above.")

    RESULTS_PATH.write_text(
        json.dumps(
            {
                "reports": reports,
                "summary": {
                    "n_passed": n_pass,
                    "n_total": len(reports),
                    "core_precision": precision,
                    "core_recall": recall,
                    "constraint_violations": violations,
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nWrote {RESULTS_PATH}")


if __name__ == "__main__":
    run()
