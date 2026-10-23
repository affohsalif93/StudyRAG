"""Builds the prerequisite graph: extracts the subset of the handbook's
prerequisite/recommended-requirement text that names another MSInf
elective, resolves it against the module catalog, and loads the
resulting edges into Neo4j.
"""

from __future__ import annotations

import difflib
import sqlite3
from typing import Literal

from neo4j import GraphDatabase
from openai import OpenAI
from pydantic import BaseModel, Field

from studyrag.config import CHAT_MODEL, NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER
from studyrag.observability import get_openai_client
from studyrag.recommender.prompts import load_prompt


class PrerequisiteItem(BaseModel):
    title: str = Field(description="Title of the other MSInf module.")
    necessity: Literal["hard", "recommended", "good_to_know"] = Field(
        description="hard: a student who skipped it would struggle badly, or the content directly "
        "builds on it (e.g. 'Advanced X'/'X II' naming 'X'). recommended: a real head start, but "
        "catchable during the module. good_to_know: minor, contextual overlap only."
    )
    reason: str = Field(description="One short sentence grounding the necessity judgment in the subject matter, not just the handbook's wording.")


class PrerequisiteExtraction(BaseModel):
    msinf_prerequisites: list[PrerequisiteItem] = Field(
        description="Other MSInf Master's elective modules explicitly named or clearly identifiable "
        "as prior knowledge for this module. Only a specific Master's-level elective counts — never "
        "a generic skill/topic phrase, and never a Bachelor's-level course."
    )
    external_prerequisite_note: str = Field(
        description="A short summary of any other prerequisite knowledge mentioned (Bachelor's "
        "courses, generic skills/topics) that is not a specific MSInf elective — human reference "
        "only, never a graph edge."
    )
    reason: str = Field(description="One short sentence.")


def extract_prerequisites(
    module_title: str,
    prerequisites_text: str,
    recommended_requirements_text: str,
    client: OpenAI | None = None,
    model: str = CHAT_MODEL,
) -> PrerequisiteExtraction:
    client = client or get_openai_client()
    response = client.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": load_prompt("prerequisite_extraction_prompt")},
            {
                "role": "user",
                "content": (
                    f"Module: {module_title}\n\n"
                    f"Prerequisites field: {prerequisites_text or '(none)'}\n\n"
                    f"Recommended requirements field: {recommended_requirements_text or '(none)'}"
                ),
            },
        ],
        response_format=PrerequisiteExtraction,
    )
    return response.choices[0].message.parsed


def resolve_module_title(title: str, catalog_titles: list[str]) -> str | None:
    """Exact match, then a word-token prefix match, then fuzzy as a last
    resort -- returns None rather than guessing when nothing is close
    enough. The prefix step matters for Roman-numeral course families:
    character-level similarity alone ranks "Automotive Engineering I"
    closer to "...III" than to its real match "...I - Longitudinal
    Dynamics", since "I"/"III" look similar as strings but aren't as
    tokens. An ambiguous prefix (several candidates share the same
    leading tokens) also returns None.
    """
    if title in catalog_titles:
        return title

    query_tokens = title.split()
    prefix_matches = [
        c for c in catalog_titles if c.split()[: len(query_tokens)] == query_tokens and len(c.split()) > len(query_tokens)
    ]
    if len(prefix_matches) == 1:
        return prefix_matches[0]
    if len(prefix_matches) > 1:
        return None

    close = difflib.get_close_matches(title, catalog_titles, n=1, cutoff=0.85)
    return close[0] if close else None


def get_neo4j_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def get_prerequisite_graph(driver) -> dict:
    """The whole current handbook-derived graph as nodes and edges.
    `kind: "handbook"` distinguishes these from tracks.py's "goal" edges,
    which connect a module to a career track from curation, not the
    regulation text.
    """
    with driver.session() as session:
        nodes = [
            {"module_id": r["module_id"], "title": r["title"], "kind": "module"}
            for r in session.run("MATCH (m:Module) RETURN m.module_id AS module_id, m.title AS title")
        ]
        edges = [
            {
                "source": r["prereq_id"],
                "target": r["module_id"],
                "kind": "handbook",
                "necessity": r["necessity"],
                "reason": r["reason"],
            }
            for r in session.run(
                "MATCH (p:Module)-[r:RECOMMENDED_BEFORE]->(m:Module) "
                "RETURN p.module_id AS prereq_id, m.module_id AS module_id, r.necessity AS necessity, r.reason AS reason"
            )
        ]
    return {"nodes": nodes, "edges": edges}


def load_prerequisite_edges(driver, edges: list[dict]) -> None:
    """MERGE, not CREATE, so re-running this after re-extraction never
    duplicates nodes or edges.
    """
    with driver.session() as session:
        for e in edges:
            session.run(
                "MERGE (m:Module {module_id: $module_id}) SET m.title = $module_title "
                "MERGE (p:Module {module_id: $prereq_id}) SET p.title = $prereq_title "
                "MERGE (p)-[r:RECOMMENDED_BEFORE]->(m) "
                "SET r.necessity = $necessity, r.reason = $reason",
                module_id=e["module_id"],
                module_title=e["module_title"],
                prereq_id=e["prereq_id"],
                prereq_title=e["prereq_title"],
                necessity=e["necessity"],
                reason=e["reason"],
            )


def build_prerequisite_graph(conn: sqlite3.Connection, titles: list[str], client: OpenAI | None = None) -> dict:
    """Runs extraction for the given module titles, resolves each named
    prerequisite against the full module catalog, and returns a report:
    {"edges": [...], "unresolved": [...], "external_notes": {...}} — does
    NOT write to Neo4j itself, so callers can inspect before loading.
    """
    client = client or get_openai_client()
    catalog_rows = conn.execute("SELECT DISTINCT module_id, title FROM modules").fetchall()
    catalog_titles = [row[1] for row in catalog_rows]
    title_to_id = {row[1]: row[0] for row in catalog_rows}

    edges: list[dict] = []
    unresolved: list[dict] = []
    external_notes: dict[str, str] = {}

    for title in titles:
        row = conn.execute(
            "SELECT module_id, title, prerequisites, recommended_requirements FROM modules WHERE title = ?", (title,)
        ).fetchone()
        if row is None:
            unresolved.append({"module": title, "issue": "module not found in catalog"})
            continue
        module_id, module_title, prereq_text, rec_text = row

        extraction = extract_prerequisites(module_title, prereq_text or "", rec_text or "", client=client)
        if extraction.external_prerequisite_note:
            external_notes[module_title] = extraction.external_prerequisite_note

        for item in extraction.msinf_prerequisites:
            resolved = resolve_module_title(item.title, catalog_titles)
            if resolved is None:
                unresolved.append({"module": module_title, "named_prerequisite": item.title, "issue": "no catalog match"})
                continue
            if resolved == module_title:
                continue  # a module can't be its own prerequisite — guards a possible self-match
            edges.append(
                {
                    "module_id": module_id,
                    "module_title": module_title,
                    "prereq_id": title_to_id[resolved],
                    "prereq_title": resolved,
                    "necessity": item.necessity,
                    "reason": item.reason,
                }
            )

    return {"edges": edges, "unresolved": unresolved, "external_notes": external_notes}
