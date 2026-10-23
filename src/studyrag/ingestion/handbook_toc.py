"""Parse the handbook's own front-matter table of contents (pages 1-11) into
a module_id -> {category, area/faculty, breadcrumb, expected page} lookup.

This replaces tracking section headings while walking the 569 body pages
(see studyrag-decisions-log.md, 2026-10-14): the TOC already states every
module's area/faculty and page, as literal text, once, up front.
"""

from __future__ import annotations

import re
from typing import TypedDict

from studyrag.ingestion.pdf_text import PAGE_BREAK

_SKIP_PREFIX = "Modules in the area of"

# The handbook's own top-level TOC branches, mapped to the PO's own terms
# (PO §4 Abs.2 lists exactly these as the Master's components besides the
# thesis: Wahlpflicht-Informatik, Anwendungsbereich, Seminar, Praktikum,
# Kolloquium). Found by reading the actual TOC end-to-end, not guessed —
# "Electives"/"Applied Courses" alone missed the tail section entirely.
TOP_LEVEL_CATEGORIES = {
    "Electives": "electives_informatik",
    "Applied Courses": "applied_courses",
    "Labs, Seminars, Colloquiums": "labs_seminars_colloquiums",  # bundles Seminar/Praktikum/Kolloquium modules
    "Master Thesis": "thesis",
    "Scientific Integrity": "other_requirement",
}

# The 5 areas as the handbook's English TOC actually spells them (not a
# guessed translation of the PO's German names) — see studyrag-decisions-log.md.
KNOWN_AREAS = {
    "Theoretical Computer Science",
    "Visual Computing & Interaction",
    "Hardware/Software Systems",
    "AI & Data",
    "Software methods, tools",
}

# One TOC line is either "[id] Title.....page >" (a module) or
# "Name.....page >" (an area/faculty/top-level heading).
_TOC_LINE_RE = re.compile(
    r"^(?:\[(?P<module_id>\d+)\]\s*)?(?P<name>.+?)\.{2,}\s*(?P<page>\d+)\s*>\s*$"
)


class TocEntry(TypedDict):
    wahlpflicht_category: str | None  # "electives_informatik" | "applied_courses" | None
    area: str | None                  # set only when category == electives_informatik
    contributing_faculty: str | None  # set only when category == applied_courses
    area_breadcrumb: list[str]
    toc_title: str
    toc_page: int


def parse_toc(front_matter_text: str) -> dict[str, list[TocEntry]]:
    """Build the module_id -> [TocEntry, ...] lookup from the front-matter text.

    A list, not a single entry, because a module can genuinely be
    cross-listed under two areas/faculties with identical content (found by
    running this against the real handbook: module 1215842 "Data Driven
    Medicine" appears once under AI & Data, page 199, and once under
    Medicine, page 515) — collapsing to one entry would silently discard
    one of two real, different listing contexts.
    """
    toc: dict[str, list[TocEntry]] = {}

    current_top_level: str | None = None
    current_category: str | None = None
    current_sub: str | None = None  # area name or contributing-faculty name

    lines = [
        line.strip()
        for line in front_matter_text.replace(PAGE_BREAK, "\n").splitlines()
        if line.strip() and not line.strip().startswith(_SKIP_PREFIX)
    ]

    i = 0
    while i < len(lines):
        line = lines[i]
        match = _TOC_LINE_RE.match(line)

        if not match and line.startswith("[") and i + 1 < len(lines):
            # A long module title wrapped onto the next physical line before
            # its "....page >" suffix — merge the two lines and retry, rather
            # than letting the continuation be mistaken for a new heading.
            merged = f"{line} {lines[i + 1]}"
            retry = _TOC_LINE_RE.match(merged)
            if retry:
                match = retry
                i += 1  # the continuation line is consumed too

        if not match:
            i += 1
            continue

        name = match.group("name").strip()
        page = int(match.group("page"))
        module_id = match.group("module_id")

        if module_id:
            breadcrumb = [n for n in (current_top_level, current_sub) if n]
            entry: TocEntry = {
                "wahlpflicht_category": current_category,
                "area": current_sub if current_category == "electives_informatik" else None,
                "contributing_faculty": current_sub if current_category == "applied_courses" else None,
                "area_breadcrumb": breadcrumb,
                "toc_title": name,
                "toc_page": page,
            }
            toc.setdefault(module_id, []).append(entry)
        elif name in TOP_LEVEL_CATEGORIES:
            current_top_level = name
            current_category = TOP_LEVEL_CATEGORIES[name]
            current_sub = None
        else:
            # Anything else at this point is an area heading (under Electives)
            # or a contributing-faculty heading (under Applied Courses, etc.).
            # Whether an "area" name actually matches KNOWN_AREAS is a
            # parser/normalization concern (flagged there), not the extractor's.
            current_sub = name

        i += 1

    return toc
