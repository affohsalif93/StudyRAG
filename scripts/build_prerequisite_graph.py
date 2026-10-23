"""Extracts the prerequisite graph from every module's
prerequisites/recommended_requirements text and loads it into Neo4j.
Safe to re-run from scratch (MERGE, not CREATE).
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "studyrag.db"


def main() -> None:
    load_dotenv(REPO_ROOT / ".env")
    from studyrag.recommender.prerequisites import build_prerequisite_graph, get_neo4j_driver, load_prerequisite_edges

    conn = sqlite3.connect(DB_PATH)
    titles = [row[0] for row in conn.execute("SELECT DISTINCT title FROM modules WHERE title IS NOT NULL")]
    print(f"Extracting prerequisites for {len(titles)} modules...")

    report = build_prerequisite_graph(conn, titles)
    print(f"Edges found: {len(report['edges'])}")
    for e in report["edges"]:
        print(f" - [{e['necessity']}] {e['prereq_title']} -> {e['module_title']} ({e['reason']})")
    print(f"Unresolved (needs review): {len(report['unresolved'])}")
    for u in report["unresolved"]:
        print(" -", u)

    driver = get_neo4j_driver()
    try:
        load_prerequisite_edges(driver, report["edges"])
    finally:
        driver.close()
    print(f"Loaded {len(report['edges'])} edges into Neo4j.")


if __name__ == "__main__":
    main()
