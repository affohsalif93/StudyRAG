"""Extractor + parser for the POs and ÜPO: articles (§, Abs.), not tables,
so this is a different anchor than the handbook's "Module titel".
"""

from __future__ import annotations

import re
from typing import TypedDict

# "§4 Title" and "§ 10 Title" both occur (inconsistent spacing in the
# source). The title is capped at the first "(" so a case like
# "§ 12 Title (1) Die..." (heading and its first Absatz on the same
# source line) doesn't swallow the "(1)" into the title.
_PARAGRAPH_RE = re.compile(r"(?m)^§\s?(?P<num>\d+[a-z]?)\s+(?P<title>[^\n(]+)")

# A long § heading can wrap onto a second physical line. A wrapped first
# line ends mid-phrase -- on a comma, "und", "oder", or a hyphenated
# line-break -- real (non-wrapped) titles don't.
_TITLE_WRAP_SUFFIXES = (",", " und", " oder", "-")

# An Absatz marker: "(N)" where N is small (<=30) and immediately followed
# by a capital letter or whitespace-then-capital -- rules out an unrelated
# parenthetical number like a percentage or a year citation.
_ABSATZ_RE = re.compile(r"\((?P<num>\d{1,2})\)\s*(?=[A-ZÄÖÜ])")

# A table-of-contents line ("§9 Title ......... 6") looks exactly like a
# real paragraph heading to _PARAGRAPH_RE. A plain length cutoff isn't
# reliable -- a long wrapped title's dot-leader filler can itself run past
# 100+ characters. What's distinctive is the shape: a TOC entry's entire
# body is nothing but a short label, a dot-leader, and a bare page number.
_TOC_LINE_RE = re.compile(r"^[^\n]{0,80}\.{3,}\s*\d+\s*$")

# The ÜPO also contains template/example annexes -- boilerplate text
# showing individual programs how to phrase their own §, reusing the same
# § numbers with placeholder markers like "Anmerkung:", "Oder:" (or:), "∅".
# Tagged, not silently mixed in as equally authoritative.
_TEMPLATE_MARKER_RE = re.compile(r"Anmerkung:|^Oder:|einfügen|ergänzen|∅", re.MULTILINE)

# A cross-reference to another document's paragraph, e.g. "§ 9 ÜPO" or
# "§ 10 Abs. 8 ÜPO" — the exact pattern the early-master-cap case needed
# (Bachelor PO § 9 only lists eligibility; the actual cap is "§ 9 Abs. 1
# ÜPO", a cross-reference the Bachelor PO text itself contains).
_CROSS_REF_RE = re.compile(r"§\s?\d+[a-z]?(?:\s+Abs\.\s*\d+)?\s+(ÜPO|PO)\b")

# A number that's plausibly a CP or percentage value stated in the rule
# text, for the numeric_value field — intentionally loose (parser/human
# review refines it further; this is a first-pass signal, not a final rule
# engine value).
_NUMERIC_RE = re.compile(r"\b(\d+)\s*CP\b")


# Every page carries this footer, immediately followed by the next page's
# header, which otherwise leaks mid-sentence into rule text. No
# page_start/page_end is tracked for rules (unlike modules), so unlike the
# handbook's strip this doesn't need to preserve the page-break character.
_PAGE_FOOTER_RE = re.compile(
    r"\f?\s*NUMMER\s+\S+(?:\s+\d+/\d+)?\s*\n"
    r"HERAUSGEGEBEN IM AUFTRAGE DES REKTORS VON DER ABTEILUNG 1\.1 DES DEZERNATES 1\.0 DER RWTH AACHEN\s*\n?"
    r".*?akad@zhv\.rwth-aachen\.de\s*\n?",
    re.DOTALL,
)


def strip_page_boilerplate(text: str) -> str:
    return _PAGE_FOOTER_RE.sub(" ", text)


def _resolve_title(text: str, match: re.Match) -> tuple[str, int]:
    """Returns (full title, offset where the heading actually ends).

    Decided in Python, not the regex, so a short second line only gets
    folded into the title when line 1 genuinely looks cut off (ends in a
    comma/"und"/"oder"/hyphen) — otherwise a short real body line right
    after the heading would wrongly get swallowed as "title".
    """
    title_line1 = match.group("title").strip()
    heading_end = match.end()  # right before the newline after line 1

    if not title_line1.endswith(_TITLE_WRAP_SUFFIXES):
        return title_line1, heading_end

    line2_start = heading_end + 1  # skip the newline itself
    line2_end = text.find("\n", line2_start)
    if line2_end == -1:
        return title_line1, heading_end

    line2 = text[line2_start:line2_end].strip()
    if not line2 or len(line2) > 80 or "(" in line2:
        return title_line1, heading_end  # doesn't look like a title continuation

    return f"{title_line1} {line2}", line2_end


class RuleBlock(TypedDict):
    paragraph: str
    title: str
    text: str


def split_into_rule_blocks(text: str) -> list[RuleBlock]:
    """Anchor on '§ N <title>', slice between consecutive occurrences —
    same anchor-to-anchor principle as the handbook's module splitting.
    Table-of-contents lines (same heading pattern, almost no body before
    the next §) are dropped, not returned as pseudo-paragraphs.
    """
    text = strip_page_boilerplate(text)
    matches = list(_PARAGRAPH_RE.finditer(text))
    blocks: list[RuleBlock] = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        title, heading_end = _resolve_title(text, match)
        body_after_heading = text[heading_end:end].strip()
        if _TOC_LINE_RE.match(body_after_heading):
            continue  # a TOC dotted-page-reference line, not a real paragraph
        blocks.append(
            {
                "paragraph": match.group("num"),
                "title": title,
                "text": text[match.start():end],
            }
        )
    return blocks


def split_into_absatz(paragraph_text: str) -> list[tuple[str | None, str]]:
    """Split one §'s text into (absatz_number_or_None, text) pieces. A
    paragraph with no "(N)" markers at all (some are a single sentence)
    yields one piece with absatz_number=None.
    """
    matches = list(_ABSATZ_RE.finditer(paragraph_text))
    if not matches:
        return [(None, paragraph_text.strip())]

    pieces: list[tuple[str | None, str]] = []
    if matches[0].start() > 0:
        preamble = paragraph_text[: matches[0].start()].strip()
        if preamble:
            pieces.append((None, preamble))

    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(paragraph_text)
        pieces.append((match.group("num"), paragraph_text[match.end():end].strip()))
    return pieces


def parse_rule_block(block: RuleBlock, source_id: str) -> list[dict]:
    """One §'s block -> one raw rule record per Absatz (schema: id implied
    by caller, source_id, paragraph, absatz, text, numeric_value,
    cross_reference, verification_status)."""
    is_template = bool(_TEMPLATE_MARKER_RE.search(block["text"]))
    records: list[dict] = []
    for absatz_num, absatz_text in split_into_absatz(block["text"]):
        cross_ref_match = _CROSS_REF_RE.search(absatz_text)
        numeric_matches = _NUMERIC_RE.findall(absatz_text)
        records.append(
            {
                "source_id": source_id,
                "paragraph": block["paragraph"],
                "paragraph_title": block["title"],
                "absatz": absatz_num,
                "text": absatz_text,
                "numeric_values_cp": [int(v) for v in numeric_matches],
                "cross_reference": cross_ref_match.group(0) if cross_ref_match else None,
                "is_template_example": is_template,
                "verification_status": "template_example" if is_template else "verified_in_source",
            }
        )
    return records
