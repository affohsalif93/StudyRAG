"""Copies the prerequisite graph (Module nodes + RECOMMENDED_BEFORE
edges) from a source Neo4j instance to a target one, e.g. local dev ->
a fresh Neo4j Aura instance for deployment. Avoids re-running
scripts/build_prerequisite_graph.py (and re-spending OpenAI cost) against
Aura directly.

Usage:
    python scripts/migrate_neo4j_graph.py \\
        --source-uri bolt://localhost:7687 --source-user neo4j --source-password studyrag_dev_password \\
        --target-uri neo4j+s://<id>.databases.neo4j.io --target-user neo4j --target-password <aura-password>
"""

from __future__ import annotations

import argparse

from neo4j import GraphDatabase


def read_graph(driver) -> list[dict]:
    with driver.session() as session:
        rows = session.run(
            "MATCH (p:Module)-[r:RECOMMENDED_BEFORE]->(m:Module) "
            "RETURN p.module_id AS prereq_id, p.title AS prereq_title, "
            "m.module_id AS module_id, m.title AS module_title, "
            "r.necessity AS necessity, r.reason AS reason"
        )
        return [dict(r) for r in rows]


def write_graph(driver, edges: list[dict]) -> None:
    with driver.session() as session:
        for e in edges:
            session.run(
                "MERGE (m:Module {module_id: $module_id}) SET m.title = $module_title "
                "MERGE (p:Module {module_id: $prereq_id}) SET p.title = $prereq_title "
                "MERGE (p)-[r:RECOMMENDED_BEFORE]->(m) "
                "SET r.necessity = $necessity, r.reason = $reason",
                **e,
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-uri", required=True)
    parser.add_argument("--source-user", required=True)
    parser.add_argument("--source-password", required=True)
    parser.add_argument("--target-uri", required=True)
    parser.add_argument("--target-user", required=True)
    parser.add_argument("--target-password", required=True)
    args = parser.parse_args()

    source = GraphDatabase.driver(args.source_uri, auth=(args.source_user, args.source_password))
    target = GraphDatabase.driver(args.target_uri, auth=(args.target_user, args.target_password))
    try:
        edges = read_graph(source)
        print(f"Read {len(edges)} edges from {args.source_uri}")
        write_graph(target, edges)
        print(f"Wrote {len(edges)} edges to {args.target_uri}")
    finally:
        source.close()
        target.close()


if __name__ == "__main__":
    main()
