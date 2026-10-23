"""The chairs graph: chair nodes, the modules matched to them, and
chair-to-chair subordination edges.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CHAIRS_PATH = REPO_ROOT / "data" / "raw" / "chairs.json"


def load_chairs() -> list[dict]:
    return json.loads(CHAIRS_PATH.read_text(encoding="utf-8"))


def get_chairs_graph(conn: sqlite3.Connection) -> dict:
    chairs = load_chairs()
    chair_nodes = [
        {
            "id": c["id"],
            "name": c["name"],
            "group_type": c["group_type"],
            "informatik_number": c["informatik_number"],
            "parent_chair_id": c.get("parent_chair_id"),
        }
        for c in chairs
    ]

    rows = conn.execute(
        """
        SELECT mc.module_id, mc.chair_id, mc.matched_people_json, m.title, m.area, m.ects
        FROM module_chairs mc
        JOIN modules m ON m.module_id = mc.module_id
        """
    ).fetchall()

    # module_id isn't unique (a module can be cross-listed under two areas) -- keep the first row per id.
    by_module: dict[str, tuple] = {}
    for row in rows:
        by_module.setdefault(row[0], row)

    module_nodes = [{"module_id": r[0], "title": r[3], "area": r[4], "ects": r[5]} for r in by_module.values()]
    module_edges = [
        {"source": r[0], "target": r[1], "matched_people": json.loads(r[2]) if r[2] else []} for r in by_module.values()
    ]
    parent_edges = [{"source": c["id"], "target": c["parent_chair_id"]} for c in chairs if c.get("parent_chair_id")]

    return {
        "chairs": chair_nodes,
        "modules": module_nodes,
        "module_edges": module_edges,
        "parent_edges": parent_edges,
    }
