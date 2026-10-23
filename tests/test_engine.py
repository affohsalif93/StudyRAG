"""Pure, deterministic engine logic (no DB, no LLM) is unit-tested
directly here. recommend() itself needs a real DB + Neo4j connection and
is exercised against real data instead, in eval/run_personas.py.
"""

from __future__ import annotations

from studyrag.recommender.engine import (
    _apply_prerequisite_ordering,
    _cp_budget_note,
    _language_compatible,
    _merge_track_candidates,
    _module_exam_formats,
    _probably_not_offered,
    _weak_skill_notes,
)
from studyrag.recommender.profile import Profile


def test_no_constraint_means_everything_compatible():
    assert _language_compatible([], "en")
    assert _language_compatible(["en"], None)


def test_exact_language_match():
    assert _language_compatible(["en"], "en")
    assert not _language_compatible(["en"], "de")


def test_de_en_module_always_compatible():
    assert _language_compatible(["en"], "de_en")
    assert _language_compatible(["de"], "de_en")


def test_exam_formats_detects_written_and_oral():
    assert _module_exam_formats("Written exam or oral examination (100 %).") == {"written", "oral"}
    assert _module_exam_formats("Oral exam, group exam") == {"oral"}
    assert _module_exam_formats("Written exam (100%). Students must pass written homework.") == {"written"}


def test_exam_formats_unknown_for_unrecognized_or_missing_text():
    # Deliberately conservative: "lab"/"seminar" are never detected from
    # free text, and anything that doesn't match stays unknown rather
    # than guessed -- see engine.py's own _EXAM_FORMAT_PATTERNS comment.
    assert _module_exam_formats("Project work (100 %).") == set()
    assert _module_exam_formats(None) == set()
    assert _module_exam_formats("") == set()


def test_probably_not_offered_flags_a_real_mismatch():
    assert _probably_not_offered("winter", "summer") is True
    assert _probably_not_offered("winter", "winter") is False


def test_probably_not_offered_never_guesses_from_unknown_data():
    assert _probably_not_offered("both", "summer") is False
    assert _probably_not_offered("irregular", "summer") is False
    assert _probably_not_offered(None, "summer") is False
    assert _probably_not_offered("winter", None) is False


def test_merge_track_candidates_keeps_the_highest_layer():
    track_a = {
        "track_id": "a",
        "core": [{"module_id": "1", "module": "Shared Core in A", "ects": 6.0, "area": "x", "reason": "r"}],
        "nice_to_have": [{"module_id": "2", "module": "Shared Nice-to-have in A", "ects": 6.0, "area": "x", "reason": "r"}],
    }
    track_b = {
        "track_id": "b",
        "nice_to_have": [{"module_id": "1", "module": "Shared Core in A", "ects": 6.0, "area": "x", "reason": "r2"}],
        "core": [{"module_id": "2", "module": "Shared Nice-to-have in A", "ects": 6.0, "area": "x", "reason": "r2"}],
    }
    merged = _merge_track_candidates([track_a, track_b])
    assert merged["1"]["layer"] == "core"  # a's core beats b's nice_to_have
    assert merged["1"]["track_ids"] == {"a", "b"}
    assert merged["2"]["layer"] == "core"  # b's core beats a's nice_to_have
    assert merged["2"]["track_ids"] == {"a", "b"}


def test_merge_track_candidates_keeps_both_when_unrelated():
    track_a = {"track_id": "a", "core": [{"module_id": "1", "module": "A only", "ects": 6.0, "area": "x", "reason": "r"}]}
    track_b = {"track_id": "b", "complementary": [{"module_id": "2", "module": "B only", "ects": 6.0, "area": "x", "reason": "r"}]}
    merged = _merge_track_candidates([track_a, track_b])
    assert set(merged.keys()) == {"1", "2"}
    assert merged["1"]["track_ids"] == {"a"}
    assert merged["2"]["track_ids"] == {"b"}


def test_apply_prerequisite_ordering_moves_prereq_in_front():
    # A real hard edge never actually violates this in production data
    # today (see the function's own docstring) -- this is the synthetic
    # case that proves the guarantee is real, not just untested.
    entries = [
        {"module_id": "dependent", "foundation_first_warnings": [{"module_id": "prereq"}]},
        {"module_id": "prereq", "foundation_first_warnings": []},
    ]
    _apply_prerequisite_ordering(entries)
    assert [e["module_id"] for e in entries] == ["prereq", "dependent"]


def test_apply_prerequisite_ordering_leaves_already_correct_order_alone():
    entries = [
        {"module_id": "prereq", "foundation_first_warnings": []},
        {"module_id": "dependent", "foundation_first_warnings": [{"module_id": "prereq"}]},
    ]
    _apply_prerequisite_ordering(entries)
    assert [e["module_id"] for e in entries] == ["prereq", "dependent"]


def test_weak_skill_notes_only_surfaces_flagged_weak_skills():
    profile = Profile.model_validate(
        {
            "skills": {
                "software_design": {"level": 1, "weak": True},
                "program_analysis_and_verification": {"level": 3, "weak": False},
            }
        }
    )
    tracks = [
        {
            "track_id": "software_engineering",
            "skills_weighted": [
                {"skill": "software_design", "weight": 5, "evidence": "real evidence"},
                {"skill": "program_analysis_and_verification", "weight": 5, "evidence": "other evidence"},
            ],
        }
    ]
    notes = _weak_skill_notes(profile, tracks)
    assert len(notes) == 1
    assert notes[0]["skill"] == "software_design"
    assert notes[0]["evidence"] == "real evidence"


def test_weak_skill_notes_dedupes_across_tracks():
    profile = Profile.model_validate({"skills": {"shared_skill": {"level": 1, "weak": True}}})
    tracks = [
        {"track_id": "a", "skills_weighted": [{"skill": "shared_skill", "weight": 3, "evidence": "e1"}]},
        {"track_id": "b", "skills_weighted": [{"skill": "shared_skill", "weight": 4, "evidence": "e2"}]},
    ]
    notes = _weak_skill_notes(profile, tracks)
    assert len(notes) == 1  # not counted once per track


def test_cp_budget_note_absent_when_not_stated():
    profile = Profile.model_validate({})
    assert _cp_budget_note(profile, [{"ects": 6.0}]) is None


def test_cp_budget_note_flags_a_real_shortfall():
    profile = Profile.model_validate({"constraints": {"cp_missing_total": 100}})
    note = _cp_budget_note(profile, [{"ects": 6.0}, {"ects": 6.0}])
    assert note["total_recommended_cp"] == 12.0
    assert "doesn't cover" in note["note"]


def test_cp_budget_note_flags_full_coverage():
    profile = Profile.model_validate({"constraints": {"cp_missing_total": 10}})
    note = _cp_budget_note(profile, [{"ects": 6.0}, {"ects": 6.0}])
    assert note["total_recommended_cp"] == 12.0
    assert "covers your stated remaining CP" in note["note"]
