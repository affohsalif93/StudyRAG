"""Deterministic rule engine that turns a student profile into a layered
module recommendation. No LLM calls.
"""

from __future__ import annotations

import re
import sqlite3

from studyrag.recommender.profile import Profile
from studyrag.recommender.rule_check import check_area_requirement, check_early_master_cap
from studyrag.recommender.tracks import list_track_ids, load_track

LAYERS = ("core", "complementary", "nice_to_have")
LAYER_PRIORITY = {layer: i for i, layer in enumerate(LAYERS)}

RESEARCH_LEANING_SECTORS = {"research", "phd"}
INDUSTRY_LEANING_SECTORS = {"industry", "startup"}
THEORETICAL_AREA = "theoretical_cs"

# Only "written"/"oral" are detected from examination_terms text -- most
# modules offer "written or oral" as a real choice, and "lab"/"seminar"
# phrasing in the handbook is too inconsistent to match reliably. A
# module is excluded only if every format it offers is one to avoid.
_EXAM_FORMAT_PATTERNS = {
    "written": re.compile(r"written exam", re.IGNORECASE),
    "oral": re.compile(r"oral exam", re.IGNORECASE),
}


def _module_exam_formats(examination_terms: str | None) -> set[str]:
    if not examination_terms:
        return set()
    return {fmt for fmt, pattern in _EXAM_FORMAT_PATTERNS.items() if pattern.search(examination_terms)}


def _research_industry_weight(area: str, sector: str) -> str:
    is_theoretical = area == THEORETICAL_AREA
    prefer_theoretical = sector in RESEARCH_LEANING_SECTORS
    return "up" if (is_theoretical == prefer_theoretical) else "down"


def _apply_research_industry_weighting(entries: list[dict], sector: str | None) -> None:
    if sector not in RESEARCH_LEANING_SECTORS | INDUSTRY_LEANING_SECTORS:
        for entry in entries:
            entry["research_industry_weight"] = None
        return
    for entry in entries:
        entry["research_industry_weight"] = _research_industry_weight(entry["area"], sector)
    entries.sort(key=lambda e: 0 if e["research_industry_weight"] == "up" else 1)


def _apply_prerequisite_ordering(entries: list[dict]) -> None:
    """Keeps a module's own hard prerequisite ahead of it within the same
    layer, in case the weighting pass above ties them in the wrong order.
    """
    for entry in list(entries):
        for warning in entry.get("foundation_first_warnings", []):
            prereq_entry = next((e for e in entries if e["module_id"] == warning["module_id"]), None)
            if prereq_entry is None:
                continue
            if entries.index(prereq_entry) > entries.index(entry):
                entries.remove(prereq_entry)
                entries.insert(entries.index(entry), prereq_entry)


def _weighting_note(sector: str | None) -> str:
    if sector in RESEARCH_LEANING_SECTORS:
        return "Ordered for a research/PhD lean: theoretical modules are emphasized first within each layer."
    if sector in INDUSTRY_LEANING_SECTORS:
        return "Ordered for an industry lean: applied modules are emphasized first within each layer."
    return "No research-vs-industry lean stated, so modules are shown in this track's own order."


def _language_compatible(wanted: list[str], module_language: str | None) -> bool:
    if not wanted or not module_language:
        return True
    if module_language == "de_en":
        return True
    return module_language in wanted


def _hard_unmet_prerequisites(driver, module_id: str, passed_ids: set[str]) -> list[dict]:
    with driver.session() as session:
        result = session.run(
            "MATCH (p:Module)-[r:RECOMMENDED_BEFORE {necessity: 'hard'}]->(m:Module {module_id: $module_id}) "
            "RETURN p.module_id AS prereq_id, p.title AS prereq_title, r.reason AS reason",
            module_id=module_id,
        )
        return [
            {"module_id": r["prereq_id"], "title": r["prereq_title"], "reason": r["reason"]}
            for r in result
            if r["prereq_id"] not in passed_ids
        ]


def _build_entry(conn: sqlite3.Connection, driver, item: dict, layer: str, passed_ids: set[str]) -> dict | None:
    module_id = item["module_id"]
    if module_id in passed_ids:
        return None

    row = conn.execute(
        "SELECT language, cycle, examination_terms, page_start, page_end FROM modules WHERE module_id = ?",
        (module_id,),
    ).fetchone()
    db_language, cycle, examination_terms, page_start, page_end = row if row else (None, None, None, None, None)

    unmet_hard = _hard_unmet_prerequisites(driver, module_id, passed_ids)

    return {
        "module": item["module"],
        "module_id": module_id,
        "ects": item["ects"],
        "area": item["area"],
        "layer": layer,
        "reason": item["reason"],
        "cycle": cycle,
        "language": db_language,
        "exam_formats": sorted(_module_exam_formats(examination_terms)),
        "handbook_page_start": page_start,
        "handbook_page_end": page_end,
        "foundation_first_warnings": unmet_hard,
        "research_industry_weight": None,
        "probably_not_offered_next_semester": None,
    }


def _probably_not_offered(cycle: str | None, wanted_semester: str | None) -> bool:
    if not cycle or not wanted_semester or cycle in ("both", "irregular"):
        return False
    return cycle != wanted_semester


def _merge_track_candidates(tracks: list[dict]) -> dict[str, dict]:
    """Collects every selected track's modules into one map, keyed by
    module id. A module named by more than one track keeps the higher
    layer (core beats complementary beats nice_to_have).
    """
    merged: dict[str, dict] = {}
    for track in tracks:
        for layer in LAYERS:
            for item in track.get(layer, []):
                module_id = item["module_id"]
                if module_id not in merged:
                    merged[module_id] = {"item": item, "layer": layer, "track_ids": {track["track_id"]}}
                    continue
                merged[module_id]["track_ids"].add(track["track_id"])
                if LAYER_PRIORITY[layer] < LAYER_PRIORITY[merged[module_id]["layer"]]:
                    merged[module_id]["item"] = item
                    merged[module_id]["layer"] = layer
    return merged


def _weak_skill_notes(profile: Profile, tracks: list[dict]) -> list[dict]:
    """Surfaces a flagged-weak skill's real evidence from the track(s)
    that name it. Doesn't try to link a weak skill to a specific
    foundation module -- the schema has no such mapping.
    """
    notes: list[dict] = []
    seen_skills: set[str] = set()
    for track in tracks:
        for skill_entry in track.get("skills_weighted", []):
            skill_name = skill_entry["skill"]
            if skill_name in seen_skills:
                continue
            student_skill = profile.skills.get(skill_name)
            if student_skill is not None and student_skill.weak:
                seen_skills.add(skill_name)
                notes.append(
                    {
                        "skill": skill_name,
                        "track_id": track["track_id"],
                        "weight": skill_entry.get("weight"),
                        "evidence": skill_entry.get("evidence"),
                    }
                )
    return notes


def _cp_budget_note(profile: Profile, entries: list[dict]) -> dict | None:
    if profile.constraints is None or profile.constraints.cp_missing_total is None:
        return None
    total_cp = sum(e["ects"] for e in entries)
    missing = profile.constraints.cp_missing_total
    if total_cp >= missing:
        note = "This recommendation alone covers your stated remaining CP -- you don't need all of it to finish."
    else:
        note = "This recommendation alone doesn't cover your stated remaining CP -- you'll need electives beyond this one goal too."
    return {"total_recommended_cp": total_cp, "cp_missing_total": missing, "note": note}


def recommend(profile: Profile, conn: sqlite3.Connection, driver) -> dict:
    if not profile.targets:
        return {"error": "No target set in the profile — the job_title stage must be answered first."}

    tracks = []
    for target in profile.targets:
        if target.track_id not in list_track_ids():
            return {"error": f"Unknown track_id {target.track_id!r} — no track file exists for it yet."}
        tracks.append(load_track(target.track_id))

    primary_target = profile.targets[0]
    passed_ids = {p.module_id for p in profile.progress.passed}
    wanted_languages = profile.constraints.language if profile.constraints else []
    wanted_semester = profile.constraints.next_semester if profile.constraints else None
    avoided_exam_formats = set()
    if profile.work_style is not None:
        avoided_exam_formats.update(profile.work_style.exam_formats_avoid)
    if profile.constraints is not None:
        avoided_exam_formats.update(profile.constraints.exam_formats_avoid)

    practical_skills: list[dict] = []
    seen_practical_skills: set[str] = set()
    for track in tracks:
        for ps in track.get("practical_skills", []):
            if ps["skill"] not in seen_practical_skills:
                seen_practical_skills.add(ps["skill"])
                practical_skills.append(ps)

    result = {
        "target": {"job_title": primary_target.job_title, "track_id": primary_target.track_id, "track_title": tracks[0]["title"]},
        "targets": [
            {"job_title": t.job_title, "track_id": t.track_id, "track_title": tr["title"]}
            for t, tr in zip(profile.targets, tracks)
        ],
        "core": [],
        "complementary": [],
        "nice_to_have": [],
        "excluded": [],
        "practical_skills": practical_skills,
        "weak_skill_notes": _weak_skill_notes(profile, tracks),
        "note": _weighting_note(primary_target.sector),
    }

    merged = _merge_track_candidates(tracks)
    for module_id, info in merged.items():
        item, layer = info["item"], info["layer"]
        entry = _build_entry(conn, driver, item, layer, passed_ids)
        if entry is None:
            result["excluded"].append({"module": item["module"], "reason": "already passed"})
            continue
        if not _language_compatible(wanted_languages, entry["language"]):
            result["excluded"].append({"module": item["module"], "reason": f"language ({entry['language']}) doesn't match {wanted_languages}"})
            continue
        offered_formats = set(entry["exam_formats"])
        if avoided_exam_formats and offered_formats and offered_formats.issubset(avoided_exam_formats):
            result["excluded"].append(
                {"module": item["module"], "reason": f"only offered as {sorted(offered_formats)} exam(s), which you want to avoid"}
            )
            continue
        entry["probably_not_offered_next_semester"] = _probably_not_offered(entry["cycle"], wanted_semester)
        result[layer].append(entry)

    for layer in LAYERS:
        _apply_research_industry_weighting(result[layer], primary_target.sector)
        _apply_prerequisite_ordering(result[layer])

    all_recommended_entries = result["core"] + result["complementary"] + result["nice_to_have"]
    result["rule_check"] = {
        "area_requirement": check_area_requirement(conn, passed_ids, all_recommended_entries),
        "early_master_cap": check_early_master_cap(profile),
    }
    result["cp_budget"] = _cp_budget_note(profile, all_recommended_entries)

    return result
