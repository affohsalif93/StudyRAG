"""Extractor for the handbook's body (pages 12-569): split into module
blocks by anchor, then slice each block's known labels into raw field
values. No lookups, no judgment calls — see studyrag-handbook-module-schema.md
for the extractor/parser split this implements.
"""

from __future__ import annotations

import re
from typing import TypedDict

from studyrag.ingestion.handbook_toc import TOP_LEVEL_CATEGORIES, TocEntry
from studyrag.ingestion.pdf_text import page_of

MODULE_ANCHOR = "Module titel"

# Some labels wrap across two physical text lines in the extracted text.
# Joining them first means the label-slicing below can treat every label as
# one contiguous string, without losing the bullet-list line breaks inside
# field *values* (those newlines are left alone).
_WRAPPED_LABELS = [
    ("Learning Objectives/\nLearning Outcomes", "Learning Objectives/ Learning Outcomes"),
    ("Teaching and Learning\nMethods", "Teaching and Learning Methods"),
    ("(Study-Specific)\nPrerequisites", "(Study-Specific) Prerequisites"),
    ("(recommended)\nRequirements", "(recommended) Requirements"),
    ("Examination duration\n(min)", "Examination duration (min)"),
]

# Order matters: this is the sequence the labels actually appear in, and
# parsing relies on searching for each one only after the previous one was
# found, so a label's text appearing inside a free-text field (e.g. the
# word "Language" inside Content) can't be mistaken for the real label.
_FIELD_LABELS: list[tuple[str, str]] = [
    ("Module titel", "_title_and_type"),  # special-cased: "Title (Type)"
    ("Identifier", "module_id"),
    ("Version", "version"),
    ("Duration (Semester)", "duration_raw"),
    ("Cycle (Semester)", "cycle_raw"),
    ("Valid from", "valid_from_raw"),
    ("Valid until", "valid_until_raw"),
    ("Module level", "level_raw"),
    ("Content", "content"),
    ("Learning Objectives/ Learning Outcomes", "learning_objectives"),
    ("Teaching and Learning Methods", "teaching_methods"),
    ("(Study-Specific) Prerequisites", "prerequisites"),
    ("(recommended) Requirements", "recommended_requirements"),
    ("References", "references"),
    ("Language", "language_raw"),
    ("Examination Terms", "examination_terms"),
    ("Miscellaneous", "miscellaneous"),
    ("Module coordinator", "coordinator"),
    ("ECTS Credits", "ects"),
    ("Contact time (WSH)", "contact_time_wsh"),
    ("Examination duration (min)", "examination_duration_min_raw"),
    ("Total hours (h)", "total_hours"),
    ("Contact hours (h)", "contact_hours"),
]

_TITLE_TYPE_RE = re.compile(r"^(?P<title>.+?)\s*\((?P<module_type_raw>[^()]+)\)\s*$")

_EMPTY_VALUES = {"", "-"}

# These fields are always exactly one line in the source. Most are already
# bounded by the next label, but "Contact hours (h)" is the last label in
# the sequence, so nothing bounds it -- without this, its value would run on
# into the exam-node table. Applied to all of them as a safety net in case
# any single one's following label isn't found.
_SINGLE_LINE_FIELDS = {"ects", "contact_time_wsh", "examination_duration_min_raw", "total_hours", "contact_hours"}

# Labels are matched anchored to the start of a line (allowing leading
# whitespace), not as a free substring search. Free-text fields --
# References above all -- can contain a label's exact word mid-sentence
# (a cited paper titled "Language Models are Unsupervised...") which a
# plain substring search would wrongly match as the real label. A
# citation is always introduced by "• " and wraps onto its own lines, so
# the real label genuinely never starts a line there.
_LABEL_PATTERNS = {
    # (?![a-zA-Z]) instead of \b: several labels end in ")" (non-word char),
    # and \b doesn't match between two non-word characters (")" then a
    # space) — it would silently reject every label ending in punctuation.
    label: re.compile(r"(?m)^[ \t]*" + re.escape(label) + r"(?![a-zA-Z])")
    for label, _ in _FIELD_LABELS
}


class ModuleSpan(TypedDict):
    text: str
    start: int
    end: int


def _normalize_wrapped_labels(text: str) -> str:
    for wrapped, joined in _WRAPPED_LABELS:
        text = text.replace(wrapped, joined)
    return text


# Every page carries a footer ("Page N of 569 Module manual for...") and the
# next page starts with a repeated breadcrumb+title header. When a page
# break falls between two labels, that boilerplate lands inside whatever
# field was mid-value. Stripped here, keeping the page-break character
# itself (captured, kept via \1) so page numbering via pdf_text.page_of
# stays correct.
#
# The breadcrumb's last line is always one of the handbook's own top-level
# TOC categories (handbook_toc.TOP_LEVEL_CATEGORIES) -- built from that one
# shared list rather than a second hardcoded one, which would drift out of
# sync with it. `\s+` between words, not a literal space, because pdftotext
# line-wraps a long category name at whatever word boundary fits the page
# width (e.g. "Labs, Seminars,\nColloquiums").
_CATEGORY_BREADCRUMB_RE = "|".join(
    r"\s+".join(re.escape(word) for word in name.split(" ")) for name in TOP_LEVEL_CATEGORIES
)
_PAGE_BOILERPLATE_RE = re.compile(
    r"[ \t]*Page \d+ of \d+ Module manual for .+? \d{1,2}:\d{2}:\d{2} [ap]\.m\.\n"
    r"(\f)"
    r".*?\nComputer Science\nMSInf\n(?:" + _CATEGORY_BREADCRUMB_RE + r")\n",
    re.DOTALL,
)


def _strip_page_boilerplate(text: str) -> str:
    # \1\n, not just \1: the stripped match consumed the header's trailing
    # newline too, so without re-adding one, whatever follows (often a real
    # label) loses its line-start anchor and silently fails to match.
    return _PAGE_BOILERPLATE_RE.sub(r"\1\n", text)


def extract_clean_body_text(full_text: str) -> str:
    """``full_text`` with the repeating page footer/header boilerplate
    removed, page-break characters kept. Apply once, then do all further
    offset-based work (block splitting, page_of) against this same text.
    """
    return _strip_page_boilerplate(full_text)


def split_front_matter(full_text: str) -> int:
    """Offset in ``full_text`` where the body (module content) begins."""
    idx = full_text.find(MODULE_ANCHOR)
    if idx == -1:
        raise ValueError(f"Could not find the module anchor {MODULE_ANCHOR!r} in the document.")
    return idx


def split_into_module_blocks(full_text: str, body_start: int) -> list[ModuleSpan]:
    """Anchor-to-anchor slicing: one module is everything between one
    occurrence of ``MODULE_ANCHOR`` and the next, however many pages that
    spans. Offsets are in ``full_text``'s own coordinate space, so
    :func:`pdf_text.page_of` can be used directly on them.
    """
    starts = [m.start() for m in re.finditer(re.escape(MODULE_ANCHOR), full_text[body_start:])]
    starts = [body_start + s for s in starts]

    spans: list[ModuleSpan] = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(full_text)
        spans.append({"text": full_text[start:end], "start": start, "end": end})
    return spans


def _best_toc_entry(entries: list[TocEntry] | None, actual_page: int) -> TocEntry | None:
    """Pick the listing whose TOC page is closest to where the module was
    actually found — needed because a module can be cross-listed under two
    areas/faculties (same content, two TOC entries); see parse_toc.
    """
    if not entries:
        return None
    return min(entries, key=lambda e: abs(e["toc_page"] - actual_page))


def parse_module_block(
    span: ModuleSpan,
    full_text: str,
    toc: dict[str, list[TocEntry]],
    source_id: str,
) -> dict:
    """Slice one module's raw text block into raw field values.

    Returns a dict matching the raw schema in studyrag-handbook-module-schema.md.
    ``parse_status`` is ``"needs_review"`` whenever an expected label wasn't
    found — the block is still returned with whatever was recoverable, plus
    the full raw text, rather than raising.
    """
    text = _normalize_wrapped_labels(span["text"])

    raw: dict = {"schema_version": 1}
    missing_labels: list[str] = []

    pos = 0
    found_positions: list[tuple[str, int, int]] = []  # (field_key, label_end, label_start_of_next_search)
    for label, _field_key in _FIELD_LABELS:
        match = _LABEL_PATTERNS[label].search(text, pos)
        if match is None:
            missing_labels.append(label)
            found_positions.append((label, -1, pos))
            continue
        found_positions.append((label, match.end(), match.start()))
        pos = match.end()

    for i, (label, field_key) in enumerate(_FIELD_LABELS):
        _, label_end, label_start = found_positions[i]
        if label_end == -1:
            raw[field_key if field_key != "_title_and_type" else "title"] = None
            continue
        next_start = None
        for j in range(i + 1, len(found_positions)):
            _, next_end, next_label_start = found_positions[j]
            if next_end != -1:
                next_start = next_label_start
                break
        value = text[label_end: next_start if next_start is not None else len(text)].strip()
        if field_key in _SINGLE_LINE_FIELDS:
            value = value.split("\n", 1)[0].strip()
        if field_key == "_title_and_type":
            match = _TITLE_TYPE_RE.match(value)
            if match:
                raw["title"] = match.group("title").strip()
                raw["module_type_raw"] = match.group("module_type_raw").strip()
            else:
                raw["title"] = value
                raw["module_type_raw"] = None
        else:
            raw[field_key] = None if value in _EMPTY_VALUES else value

    module_id = raw.get("module_id")
    page_start = page_of(full_text, span["start"])
    toc_entry = _best_toc_entry(toc.get(module_id) if module_id else None, page_start)

    raw["source_id"] = source_id
    raw["page_start"] = page_start
    raw["page_end"] = page_of(full_text, max(span["end"] - 1, span["start"]))
    raw["wahlpflicht_category"] = toc_entry["wahlpflicht_category"] if toc_entry else None
    raw["area_raw"] = toc_entry["area"] if toc_entry else None
    raw["contributing_faculty_raw"] = toc_entry["contributing_faculty"] if toc_entry else None
    raw["area_breadcrumb"] = toc_entry["area_breadcrumb"] if toc_entry else []
    raw["toc_page_expected"] = toc_entry["toc_page"] if toc_entry else None
    raw["exam_nodes"] = []  # filled in separately, see the exam-node table note in studyrag-handbook-module-schema.md
    raw["parse_status"] = "needs_review" if missing_labels else "ok"
    raw["parse_method"] = "rule"
    raw["llm_notes"] = None
    raw["raw_text"] = span["text"]

    if missing_labels:
        raw["_missing_labels"] = missing_labels  # debugging aid, not part of the final schema

    return raw
