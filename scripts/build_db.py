"""Build data/studyrag.db from data/raw/sources.json and
data/processed/extracted/*.jsonl.

Safe to re-run from scratch at any time: sources is upserted, modules/rules
are wiped and re-inserted from the current JSONL files every run.

Usage: python build_db.py
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from studyrag.db.loader import create_schema, load_fts_index, load_modules, load_rules, load_sources
from studyrag.retrieval.chunks import build_module_chunks, build_rule_chunks

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "studyrag.db"
SOURCES_FILE = REPO_ROOT / "data" / "raw" / "sources.json"
EXTRACTED_DIR = REPO_ROOT / "data" / "processed" / "extracted"
MODULES_JSONL = EXTRACTED_DIR / "modules_MSInf2023_WiSe2026_en.jsonl"
RULES_JSONL_FILES = [
    EXTRACTED_DIR / "rules_po_master_2023.jsonl",
    EXTRACTED_DIR / "rules_po_bachelor_2022.jsonl",
    EXTRACTED_DIR / "rules_uepo_2026_109_de.jsonl",
]


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        create_schema(conn)
        n_sources = load_sources(conn, str(SOURCES_FILE))
        print(f"sources: {n_sources} rows upserted")

        n_modules = load_modules(conn, str(MODULES_JSONL))
        print(f"modules: {n_modules} rows loaded from {MODULES_JSONL.name}")

        total_rules = 0
        for path in RULES_JSONL_FILES:
            n = load_rules(conn, str(path))
            total_rules += n
            print(f"rules: {n} rows loaded from {path.name}")
        print(f"rules: {total_rules} total")

        # Same chunks the vector store embeds, indexed for BM25 too, so
        # the two can be fused in hybrid search.
        chunks = build_module_chunks(conn) + build_rule_chunks(conn)
        n_fts = load_fts_index(conn, chunks)
        print(f"chunks_fts: {n_fts} rows indexed for BM25")
    finally:
        conn.close()

    print(f"\nWrote {DB_PATH}")


if __name__ == "__main__":
    main()
