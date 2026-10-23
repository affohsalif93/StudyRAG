"""Re-fetches every source in data/raw/sources.json, compares against
its stored content hash, and on a real change: writes a readable diff
report, archives the old raw PDF + extracted JSONL, applies the new
version, and re-runs the parse -> DB -> embedding-index pipeline for
just the sources that changed.

A re-parsed module/rule can still come back flagged needs_review /
needs_mapping -- those rows are still loaded, same as in a normal
build, but this script prints them clearly so they don't get missed.

Usage: python scripts/refresh_sources.py (run from the repo root)
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_chunk_index
import parse_handbook
import parse_po
from build_db import EXTRACTED_DIR, MODULES_JSONL, RULES_JSONL_FILES

from studyrag.db.loader import create_schema, load_fts_index, load_modules, load_rules, load_sources
from studyrag.retrieval.chunks import build_module_chunks, build_rule_chunks
from studyrag.refresh.diff_report import build_diff_report
from studyrag.refresh.refresh import (
    apply_new_version,
    archive_old_version,
    check_source_for_changes,
    fetch_source_bytes,
    load_page_hashes,
    save_page_hashes,
    save_sources,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "data" / "raw"
SOURCES_PATH = RAW_DIR / "sources.json"
PAGE_HASHES_PATH = RAW_DIR / "page_hashes.json"
ARCHIVE_DIR = RAW_DIR / "archive"
CHANGE_REPORTS_DIR = RAW_DIR / "change_reports"
DB_PATH = REPO_ROOT / "data" / "studyrag.db"

# Only sources actually wired into the parse -> DB pipeline (build_db.py).
# uepo_2026_109_en is tracked for provenance but never parsed into rules —
# see studyrag-decisions-log.md; a change to it is reported and archived
# like any other, just not auto-reparsed.
_RULES_JSONL_BY_SOURCE = {
    "po_master_2023": EXTRACTED_DIR / "rules_po_master_2023.jsonl",
    "po_bachelor_2022": EXTRACTED_DIR / "rules_po_bachelor_2022.jsonl",
    "uepo_2026_109_de": EXTRACTED_DIR / "rules_uepo_2026_109_de.jsonl",
}


def reparse_source(source: dict) -> bool:
    """Re-runs the right extractor for one changed source. Returns True
    if re-parsed, False if this source isn't wired into the automated
    pipeline (reported, archived, but left for a manual follow-up).
    """
    source_id = source["id"]
    if source_id == "mhb_en_wise2026":
        out_prefix = str(MODULES_JSONL).removesuffix(".jsonl")
        parse_handbook.run(source["local_path"], source_id, out_prefix)
        return True
    if source_id in _RULES_JSONL_BY_SOURCE:
        parse_po.run(source["local_path"], source_id, str(_RULES_JSONL_BY_SOURCE[source_id]))
        return True
    print(f"  [{source_id}] not part of the automated parse pipeline — review and reparse manually.")
    return False


def rebuild_db_and_index() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        create_schema(conn)
        load_sources(conn, str(SOURCES_PATH))
        load_modules(conn, str(MODULES_JSONL))
        for path in RULES_JSONL_FILES:
            load_rules(conn, str(path))
        chunks = build_module_chunks(conn) + build_rule_chunks(conn)
        load_fts_index(conn, chunks)
    finally:
        conn.close()
    build_chunk_index.main()


def run() -> None:
    sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    page_hashes = load_page_hashes(PAGE_HASHES_PATH)
    today = dt.date.today().isoformat()

    any_changed = False
    any_reparsed = False
    updated_sources = []

    for source in sources:
        print(f"[{source['id']}] checking {source['url']}")
        try:
            new_bytes = fetch_source_bytes(source["url"])
        except Exception as e:
            print(f"  fetch failed: {e} — skipping, keeping current version.")
            updated_sources.append(source)
            continue

        result = check_source_for_changes(source, new_bytes, page_hashes.get(source["id"], []))
        if not result.changed:
            print("  no change.")
            updated_sources.append(source)
            continue

        any_changed = True
        print(f"  CHANGED — {len(result.changed_pages)} page(s) differ: {result.changed_pages}")

        report = build_diff_report(
            source["id"], result.old_pages, result.new_pages, result.changed_pages, source["retrieved_at"], today
        )
        CHANGE_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        report_path = CHANGE_REPORTS_DIR / f"{source['id']}_{today}.md"
        report_path.write_text(report, encoding="utf-8")
        print(f"  wrote change report: {report_path}")

        archive_old_version(source, EXTRACTED_DIR, ARCHIVE_DIR)
        new_source = apply_new_version(source, result.new_bytes, today)
        updated_sources.append(new_source)
        page_hashes[source["id"]] = result.new_page_hashes

        print(f"  NOTE: check {report_path.name} and update \"version\" in sources.json by hand if it changed.")

        if reparse_source(new_source):
            any_reparsed = True

    save_sources(SOURCES_PATH, updated_sources)
    save_page_hashes(PAGE_HASHES_PATH, page_hashes)

    if not any_changed:
        print("\nNo changes detected across all sources.")
        return

    if any_reparsed:
        print("\nRebuilding database and embedding index for the new version(s)...")
        rebuild_db_and_index()
        print("Done — the new version is searchable.")
    else:
        print("\nChanged source(s) were not part of the automated parse pipeline — no rebuild triggered.")


if __name__ == "__main__":
    run()
