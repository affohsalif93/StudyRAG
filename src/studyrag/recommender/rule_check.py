"""CP/area and early-master-cap checks against the PO, computed in code
rather than left to the LLM.
"""

from __future__ import annotations

import sqlite3

from studyrag.recommender.profile import Profile

AREA_MIN_CP = 12.0
REQUIRED_AREAS_MET = 3
REQUIRED_AREA = "theoretical_cs"

AREA_RULE_CITATION = "§ 16 Abs. 1 / § 4 Abs. 2, Prüfungsordnung Master Informatik 2023"
EARLY_MASTER_CAP_CITATION = "§ 9 Abs. 1 ÜPO (cross-referenced from § 9 Bachelor PO 2022)"


def _passed_area_cp(conn: sqlite3.Connection, passed_ids: set[str]) -> dict[str, float]:
    cp_by_area: dict[str, float] = {}
    for module_id in passed_ids:
        row = conn.execute("SELECT area, ects FROM modules WHERE module_id = ?", (module_id,)).fetchone()
        if row is None or row[0] is None:
            continue  # not a Wahlpflicht-Informatik module
        area, ects = row
        cp_by_area[area] = cp_by_area.get(area, 0.0) + (ects or 0.0)
    return cp_by_area


def _recommended_area_cp(recommended_entries: list[dict]) -> dict[str, float]:
    cp_by_area: dict[str, float] = {}
    for entry in recommended_entries:
        if entry.get("area"):
            cp_by_area[entry["area"]] = cp_by_area.get(entry["area"], 0.0) + (entry.get("ects") or 0.0)
    return cp_by_area


def check_area_requirement(conn: sqlite3.Connection, passed_ids: set[str], recommended_entries: list[dict]) -> dict:
    """Projects CP per area if the student takes every recommended
    module on top of what they've already passed. Not satisfied just
    means this one track isn't the student's whole elective plan.
    """
    combined = _passed_area_cp(conn, passed_ids)
    for area, cp in _recommended_area_cp(recommended_entries).items():
        combined[area] = combined.get(area, 0.0) + cp

    areas_meeting_minimum = sorted(area for area, cp in combined.items() if cp >= AREA_MIN_CP)
    satisfied = len(areas_meeting_minimum) >= REQUIRED_AREAS_MET and REQUIRED_AREA in areas_meeting_minimum

    return {
        "rule": (
            f"At least {REQUIRED_AREAS_MET} of the 5 elective areas need ≥{AREA_MIN_CP:g} CP each, "
            f"and one of those must be 'Theoretische Informatik' ({REQUIRED_AREA})."
        ),
        "citation": AREA_RULE_CITATION,
        "cp_by_area": {area: round(cp, 1) for area, cp in sorted(combined.items())},
        "areas_meeting_minimum": areas_meeting_minimum,
        "satisfied": satisfied,
        "basis": (
            "passed modules plus every module this recommendation currently lists (core, complementary, "
            "nice to have) -- a projection of this one track's plan, not a commitment and not the student's "
            "full elective plan across all tracks"
        ),
    }


def check_early_master_cap(profile: Profile) -> dict:
    """Only applies to a Bachelor's student taking Master's modules
    early. Profile has no field for that status, so this always
    reports "does not apply" rather than guessing.
    """
    return {
        "rule": "A Bachelor's student taking Master's modules early (Vorgezogene Mastermodule) may take at most 30 CP of them.",
        "citation": EARLY_MASTER_CAP_CITATION,
        "applies": False,
        "note": (
            f"This profile represents an enrolled MSInf student (program={profile.program!r}), not a "
            "Bachelor's student taking Master's modules early -- there's nothing for this cap to apply to here."
        ),
    }
