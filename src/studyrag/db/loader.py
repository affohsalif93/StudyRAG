"""Load data/processed/*.jsonl into data/studyrag.db. Plain functions, no
classes — same style as src/studyrag/ingestion/. modules/exam_nodes/rules
are 100% derived from the JSONL files and are wiped + re-inserted on every
call; sources is the one small, hand-maintained table, upserted by id.
See studyrag-features-and-steps.md "Database design" and
studyrag-handbook-module-schema.md for the shapes these mirror.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()


def load_sources(conn: sqlite3.Connection, sources_file: str) -> int:
    """Upsert by id — sources.json is small and hand-maintained, never wiped."""
    sources = json.loads(Path(sources_file).read_text(encoding="utf-8"))
    conn.executemany(
        """
        INSERT INTO sources (id, name, url, doc_type, version, valid_for, language, terms_note, local_path, content_hash, retrieved_at)
        VALUES (:id, :name, :url, :doc_type, :version, :valid_for, :language, :terms_note, :local_path, :content_hash, :retrieved_at)
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name, url=excluded.url, doc_type=excluded.doc_type,
            version=excluded.version, valid_for=excluded.valid_for, language=excluded.language,
            terms_note=excluded.terms_note, local_path=excluded.local_path,
            content_hash=excluded.content_hash, retrieved_at=excluded.retrieved_at
        """,
        sources,
    )
    conn.commit()
    return len(sources)


def load_fts_index(conn: sqlite3.Connection, chunks: list[dict]) -> int:
    """Wipes and repopulates chunks_fts from the given chunk list — fully
    derived from modules/rules (same chunks the vector store embeds, see
    src/studyrag/retrieval/chunks.py), never hand-edited, same wipe-and-
    reload philosophy as load_modules/load_rules.
    """
    conn.execute("DELETE FROM chunks_fts")
    conn.executemany(
        "INSERT INTO chunks_fts (chunk_id, text) VALUES (?, ?)",
        [(c["chunk_id"], c["text"]) for c in chunks],
    )
    conn.commit()
    return len(chunks)


def _read_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_modules(conn: sqlite3.Connection, jsonl_path: str) -> int:
    """Wipes modules + exam_nodes and re-inserts from the handbook JSONL.
    Safe to wipe: fully derived, never hand-edited. module_id is NOT the
    primary key (one real module is legitimately cross-listed twice, see
    studyrag-decisions-log.md) — `id` is a plain autoincrement instead.
    """
    records = _read_jsonl(jsonl_path)

    conn.execute("DELETE FROM exam_nodes")
    conn.execute("DELETE FROM modules")

    columns = [
        "module_id", "source_id", "schema_version", "title", "module_type", "version",
        "duration_semesters", "cycle", "valid_from", "valid_until", "level", "language",
        "content", "learning_objectives", "teaching_methods", "prerequisites",
        "recommended_requirements", "references", "examination_terms", "miscellaneous",
        "coordinator", "ects", "contact_time_wsh", "examination_duration_min_raw",
        "total_hours", "contact_hours", "page_start", "page_end", "wahlpflicht_category",
        "area", "contributing_faculty", "toc_page_expected", "translation_source",
        "parse_status", "parse_method", "llm_notes", "normalization_status", "raw_text",
    ]
    placeholders = ", ".join(f":{c}" for c in columns)
    quoted_columns = ", ".join(f'"{c}"' if c == "references" else c for c in columns)

    for r in records:
        row = {c: r.get(c) for c in columns}
        row["area_breadcrumb_json"] = json.dumps(r.get("area_breadcrumb", []), ensure_ascii=False)
        row["unmapped_raw_values_json"] = json.dumps(r.get("unmapped_raw_values", []), ensure_ascii=False)
        cursor = conn.execute(
            f"""
            INSERT INTO modules ({quoted_columns}, area_breadcrumb_json, unmapped_raw_values_json)
            VALUES ({placeholders}, :area_breadcrumb_json, :unmapped_raw_values_json)
            """,
            row,
        )
        module_row_id = cursor.lastrowid
        for node in r.get("exam_nodes", []):
            conn.execute(
                """
                INSERT INTO exam_nodes (module_id, title, recommended_semester_winter, recommended_semester_summer, ects, contact_time)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    module_row_id,
                    node.get("title"),
                    node.get("recommended_semester_winter"),
                    node.get("recommended_semester_summer"),
                    node.get("ects"),
                    node.get("contact_time"),
                ),
            )

    conn.commit()
    return len(records)


def load_module_chairs(conn: sqlite3.Connection, report_path: str) -> int:
    """Wipes and re-inserts module_chairs from
    scripts/link_chair_modules.py's report -- only the "matched" bucket
    (exactly-one-chair results); ambiguous/unmatched/not_applicable are
    deliberately never loaded here, see studyrag-decisions-log.md's
    chair-module-linking entry for why each stayed out. Fully derived,
    safe to rebuild from scratch.
    """
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    matched = report["matched"]

    conn.execute("DELETE FROM module_chairs")
    conn.executemany(
        "INSERT INTO module_chairs (module_id, chair_id, matched_people_json) VALUES (?, ?, ?)",
        [(m["module_id"], m["chair_id"], json.dumps(m["matched_people"], ensure_ascii=False)) for m in matched],
    )
    conn.commit()
    return len(matched)


def load_rules(conn: sqlite3.Connection, jsonl_path: str) -> int:
    """Wipes and re-inserts the rules belonging to one source document's
    JSONL file only — other sources' rules are untouched.
    """
    records = _read_jsonl(jsonl_path)
    if not records:
        return 0

    source_id = records[0]["source_id"]
    conn.execute("DELETE FROM rules WHERE source_id = ?", (source_id,))

    for r in records:
        conn.execute(
            """
            INSERT INTO rules (source_id, paragraph, paragraph_title, absatz, text,
                                numeric_values_cp_json, cross_reference, is_template_example, verification_status)
            VALUES (:source_id, :paragraph, :paragraph_title, :absatz, :text,
                    :numeric_values_cp_json, :cross_reference, :is_template_example, :verification_status)
            """,
            {
                "source_id": r["source_id"],
                "paragraph": r["paragraph"],
                "paragraph_title": r.get("paragraph_title"),
                "absatz": r.get("absatz"),
                "text": r.get("text"),
                "numeric_values_cp_json": json.dumps(r.get("numeric_values_cp", []), ensure_ascii=False),
                "cross_reference": r.get("cross_reference"),
                "is_template_example": int(bool(r.get("is_template_example"))),
                "verification_status": r.get("verification_status"),
            },
        )

    conn.commit()
    return len(records)
