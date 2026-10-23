"""Title resolution against the module catalog is pure, deterministic
logic. The extraction classifier itself is left untested, same
convention as the other classify_*_intent functions in this codebase.
"""

from __future__ import annotations

from studyrag.recommender.prerequisites import resolve_module_title

CATALOG = ["Machine Learning", "Advanced Machine Learning", "Mathematical Logic II", "Software Architecture"]


def test_exact_match_wins():
    assert resolve_module_title("Machine Learning", CATALOG) == "Machine Learning"


def test_close_fuzzy_match_resolves():
    assert resolve_module_title("the lecture Machine Learning", CATALOG) is None  # too different, below cutoff
    assert resolve_module_title("Software Architectures", CATALOG) == "Software Architecture"


def test_no_match_returns_none_rather_than_guessing():
    assert resolve_module_title("Introduction to Software Engineering", CATALOG) is None


def test_prefix_match_resolves_a_short_name_to_its_full_catalog_title():
    # "Mathematical Logic" is a word-token prefix of exactly one catalog
    # title here, so it resolves via the prefix step -- an accepted limit
    # when the short name is genuinely ambiguous (a real Bachelor's
    # "Mathematical Logic I" existed too), handled by the upstream
    # classifier only passing in names it believes name a specific elective.
    assert resolve_module_title("Mathematical Logic", CATALOG) == "Mathematical Logic II"


def test_roman_numeral_siblings_do_not_collide():
    # difflib's character-sequence ratio scores "Automotive Engineering I"
    # higher against "Automotive Engineering III" (0.96) than against its
    # true match "Automotive Engineering I - Longitudinal Dynamics" (0.67) --
    # a pure ratio match would pick the wrong course; the prefix step
    # must resolve this correctly instead.
    numeral_catalog = [
        "Automotive Engineering I - Longitudinal Dynamics",
        "Automotive Engineering II - Vertical and Lateral Dynamics",
        "Automotive Engineering III",
    ]
    assert resolve_module_title("Automotive Engineering I", numeral_catalog) == "Automotive Engineering I - Longitudinal Dynamics"


def test_ambiguous_prefix_family_returns_none_rather_than_guessing():
    ambiguous_catalog = ["Topic X: Part A", "Topic X: Part B"]
    assert resolve_module_title("Topic X", ambiguous_catalog) is None
