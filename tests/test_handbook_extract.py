"""Regression test for a real bug: extract_clean_body_text's page-boilerplate
stripper only recognized 2 of the handbook's 5 real top-level TOC categories
("Electives", "Applied Courses"), so a page break inside a module from one
of the other 3 categories (Labs/Seminars/Colloquiums, Master Thesis,
Scientific Integrity) left the next page's repeated breadcrumb+title header
unstripped -- and when that landed inside a still-open field, it leaked
straight into the parsed value. Found in production data: module 4028624's
`coordinator` field and 9033432's `examination_terms` field. See
studyrag-decisions-log.md.
"""

from __future__ import annotations

from studyrag.ingestion.handbook_extract import extract_clean_body_text

_FOOTER = "Page 562 of 569 Module manual for MSInf 2023 | Revision 2026-10-01 | 10:07:16 a.m.\n"


def _page_break(category_breadcrumb: str, title: str = "Some Module (1234567)") -> str:
    return f"{_FOOTER}\f{title}\nComputer Science\nMSInf\n{category_breadcrumb}\n"


def test_strips_electives_and_applied_courses_categories():
    for category in ("Electives", "Applied Courses"):
        text = f"before{_page_break(category)}after"
        # the page-break character (\f) is deliberately kept, plus a
        # re-added \n so whatever follows keeps its line-start anchor --
        # see _strip_page_boilerplate's own comment.
        assert extract_clean_body_text(text) == "before\f\nafter"


def test_strips_labs_seminars_colloquiums_even_when_line_wrapped():
    # The real production bug: pdftotext wraps this specific category name
    # across two lines ("Labs, Seminars,\nColloquiums"), confirmed against
    # the real extracted handbook text before writing this test.
    wrapped = "Labs, Seminars,\nColloquiums"
    text = f"before{_page_break(wrapped)}after"
    assert extract_clean_body_text(text) == "before\f\nafter"


def test_strips_master_thesis_and_scientific_integrity_categories():
    for category in ("Master Thesis", "Scientific Integrity"):
        text = f"before{_page_break(category)}after"
        assert extract_clean_body_text(text) == "before\f\nafter"


def test_real_4028624_coordinator_leak_is_fixed():
    # Shortened, real production text (module 4028624) that used to leak
    # straight into the coordinator field's value.
    leaked = (
        "Universitätsprofessor Dr. Sebastian Trimpe\n"
        "Page 562 of 569 Module manual for MSInf 2023 | Revision 2026-10-01 | 10:07:16 a.m.\n"
        "\x0cSeminar: Mathematical Concepts of Machine Learning (4028624)\n"
        "Computer Science\nMSInf\nLabs, Seminars,\nColloquiums\n"
        "ECTS Credits 4"
    )
    cleaned = extract_clean_body_text(leaked)
    assert "Page" not in cleaned
    assert "Module manual for" not in cleaned
    assert cleaned == "Universitätsprofessor Dr. Sebastian Trimpe\n\x0c\nECTS Credits 4"
