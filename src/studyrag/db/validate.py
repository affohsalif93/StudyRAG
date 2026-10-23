"""DB load validation, as reusable functions: for N randomly chosen
modules, the database row matches the PDF field by field (CP, level,
cycle, prerequisites), and the early-master-module cap round-trips
correctly as a rule that cross-references the ÜPO from the Bachelor PO.
Run via scripts/validate_db.py; kept here so it's testable on its own.
"""

from __future__ import annotations

import json
import random
import sqlite3
from pathlib import Path

from studyrag.ingestion.handbook_normalize import _CYCLE_MAP, _LEVEL_MAP
from studyrag.ingestion.pdf_text import extract_text

_CYCLE_RAW_BY_CANONICAL = {v: k for k, v in _CYCLE_MAP.items()}
_LEVEL_RAW_BY_CANONICAL = {v: k for k, v in _LEVEL_MAP.items()}


def check_random_modules(conn: sqlite3.Connection, repo_root: Path, n: int, seed: int | None) -> list[str]:
    failures: list[str] = []
    rows = conn.execute(
        """
        SELECT m.module_id, m.title, m.ects, m.level, m.cycle, m.prerequisites,
               m.page_start, m.page_end, s.local_path
        FROM modules m JOIN sources s ON m.source_id = s.id
        """
    ).fetchall()

    rng = random.Random(seed)
    sample = rng.sample(rows, min(n, len(rows)))

    for module_id, title, ects, level, cycle, prerequisites, page_start, page_end, local_path in sample:
        pdf_path = str(repo_root / local_path)
        page_text = extract_text(pdf_path, page_start, page_end)

        if title and title not in page_text:
            failures.append(f"{module_id}: title {title!r} not found on page {page_start}-{page_end}")

        if ects is not None:
            # German-locale comma decimal in the source PDF ("2,5"), not a period.
            ects_str = str(int(ects)) if ects == int(ects) else str(ects).replace(".", ",")
            if ects_str not in page_text:
                failures.append(f"{module_id}: ects {ects_str!r} not found on page {page_start}-{page_end}")

        if level:
            raw_level = _LEVEL_RAW_BY_CANONICAL.get(level)
            if raw_level and raw_level.title() not in page_text and raw_level not in page_text:
                failures.append(f"{module_id}: level {level!r} (raw {raw_level!r}) not found on page {page_start}-{page_end}")

        if cycle:
            raw_cycle = _CYCLE_RAW_BY_CANONICAL.get(cycle)
            if raw_cycle and raw_cycle not in page_text:
                failures.append(f"{module_id}: cycle {cycle!r} (raw {raw_cycle!r}) not found on page {page_start}-{page_end}")

        if prerequisites and prerequisites not in page_text:
            failures.append(f"{module_id}: prerequisites text not found verbatim on page {page_start}-{page_end}")

    print(f"Checked {len(sample)} random modules field-by-field against their source PDF pages.")
    return failures


def check_early_master_cap(conn: sqlite3.Connection) -> list[str]:
    failures: list[str] = []

    bachelor_row = conn.execute(
        """SELECT cross_reference FROM rules
           WHERE source_id = 'po_bachelor_2022' AND paragraph = '9' AND absatz = '1'"""
    ).fetchone()
    if bachelor_row is None or not bachelor_row[0]:
        failures.append("Bachelor PO § 9 Abs. 1 has no cross_reference recorded")
        return failures

    cross_ref = bachelor_row[0]
    if "ÜPO" not in cross_ref:
        failures.append(f"Bachelor PO § 9 Abs. 1 cross_reference {cross_ref!r} does not point at the ÜPO")
        return failures

    uepo_row = conn.execute(
        """SELECT numeric_values_cp_json FROM rules
           WHERE source_id = 'uepo_2026_109_de' AND paragraph = '9' AND absatz = '1'
             AND is_template_example = 0"""
    ).fetchone()
    if uepo_row is None:
        failures.append("Could not find the operative (non-template) ÜPO § 9 Abs. 1")
        return failures

    cp_values = json.loads(uepo_row[0])
    if 30 not in cp_values:
        failures.append(f"ÜPO § 9 Abs. 1 numeric values {cp_values} do not include the 30 CP early-master cap")

    print(f"Early-master-cap round-trip: Bachelor PO § 9 -> {cross_ref!r} -> ÜPO § 9 Abs. 1, CP values {cp_values}")
    return failures
