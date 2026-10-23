"""Links modules to the chair that coordinates them, by checking
whether a module's real `coordinator` name appears on a real scraped
chair page (data/raw/chairs/<id>.txt, see scrape_chairs.py) -- direct
personnel evidence, not topical inference.

Matching is accent-insensitive: the handbook's `coordinator` field
strips diacritics the real chair page keeps (e.g. "Erika Abraham" in
the DB vs. "Erika Ábrahám" on the chair's own page).

Only the matched (unambiguous) bucket is persisted, into module_chairs
(src/studyrag/db/schema.sql), wiped and reloaded every run.
Ambiguous/unmatched/not_applicable stay in the printed report and the
written JSON file for human review, never loaded.

Usage: python scripts/link_chair_modules.py (run from the repo root)
"""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from pathlib import Path

from studyrag.db.loader import create_schema, load_module_chairs

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "studyrag.db"
CHAIRS_PATH = REPO_ROOT / "data" / "raw" / "chairs.json"

_TITLE_PATTERN = re.compile(
    r"\([^)]*\)|Universit.tsprofessor(in)?|apl\.?|Professor(in)?|Prof\.?|Dr\.|rer\.|nat\.|ir\.|h\.?\s*c\.?|med\.?|phil\.?|habil\.?|-Ing\.?",
    re.IGNORECASE,
)
# Not people -- "coordinator" is sometimes the department itself (any
# chair may offer the seminar/thesis slot) or the German placeholder for
# an unfilled position. Matching these against chair pages would either
# hit every chair or none, neither of which is a real answer.
_NOT_A_PERSON = {"informatik", "n.n.", "n. n.", ""}


def clean_coordinator_name(raw: str) -> str:
    """Strips academic titles/degrees (Universitätsprofessor, Dr. rer.
    nat., honorary parentheticals like "(AAU)") down to the actual
    person name, e.g. "apl. Professor Dr. rer. nat. Thomas Noll" ->
    "Thomas Noll".
    """
    s = _TITLE_PATTERN.sub("", raw)
    return re.sub(r"\s+", " ", s).strip()


def split_coordinators(raw: str) -> list[str]:
    """A module can list several coordinators, comma-separated (e.g.
    "Christina Büsing, Arie Koster, Britta Peis") -- matching the whole
    string against a chair page would never hit even when one of them
    clearly belongs there, so each name is checked independently.
    """
    return [clean_coordinator_name(part) for part in raw.split(",")]


def fold(s: str) -> str:
    """Accent-insensitive, case-insensitive form for matching -- "Erika
    Ábrahám" and "Erika Abraham" fold to the same string.
    """
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


# A name occurring shortly after one of these phrases means "this is the
# chair's actual head/contact", not just a co-author credit or an
# incidental substring -- found directly by inspecting the real
# ambiguous cases (e.g. comsys: "headed by Prof. Dr.-Ing. Klaus Wehrle"
# vs. spice: Wehrle only appears as a paper co-author).
_HEAD_MARKERS = ["headed by", "geleitet von", "contact prof", "leitung:"]


def is_head_mention(text: str, folded_name: str) -> bool:
    for m in re.finditer(re.escape(folded_name), text):
        window = text[max(0, m.start() - 60) : m.start()]
        if any(marker in window for marker in _HEAD_MARKERS):
            return True
    return False


def name_matches(folded_name: str, text: str) -> bool:
    """Word-boundary match -- plain substring matching let "Prinz" match
    inside "Prinzipien" (German for "principles"), a real false positive
    caught by inspecting an actual ambiguous result, not hypothesized.
    """
    return re.search(rf"\b{re.escape(folded_name)}\b", text) is not None


def load_chair_texts() -> dict[str, str]:
    chairs = json.loads(CHAIRS_PATH.read_text(encoding="utf-8"))
    texts = {}
    for c in chairs:
        if not c.get("local_path"):
            continue
        path = REPO_ROOT / c["local_path"]
        if path.exists():
            texts[c["id"]] = fold(path.read_text(encoding="utf-8"))
    return texts


def run() -> None:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT DISTINCT module_id, title, coordinator FROM modules WHERE coordinator IS NOT NULL AND coordinator != ''"
    ).fetchall()
    conn.close()

    chair_texts = load_chair_texts()
    all_chairs = json.loads(CHAIRS_PATH.read_text(encoding="utf-8"))
    chair_names = {c["id"]: c["name"] for c in all_chairs}
    parent_of = {c["id"]: c["parent_chair_id"] for c in all_chairs if c.get("parent_chair_id")}

    matched: list[dict] = []
    ambiguous: list[dict] = []
    unmatched: list[dict] = []
    not_applicable: list[dict] = []

    for module_id, title, coordinator in rows:
        people = split_coordinators(coordinator)
        real_people = [p for p in people if fold(p) not in _NOT_A_PERSON and len(fold(p)) >= 4]

        if not real_people:
            not_applicable.append({"module_id": module_id, "title": title, "coordinator": coordinator})
            continue

        # chair_id -> which named person(s) were found on that chair's page
        chairs_hit: dict[str, list[str]] = {}
        head_chairs: set[str] = set()
        for person in real_people:
            folded_name = fold(person)
            for cid, text in chair_texts.items():
                if not name_matches(folded_name, text):
                    continue
                chairs_hit.setdefault(cid, []).append(person)
                if is_head_mention(text, folded_name):
                    head_chairs.add(cid)

        resolved_note = None
        if len(chairs_hit) > 1:
            # A candidate that is a recorded sub-chair of another
            # candidate (see the "sub-chair hierarchy" decisions-log
            # entry -- e.g. ths is embedded into moves) isn't a real
            # second option; collapse to the parent.
            non_subordinate = {cid for cid in chairs_hit if parent_of.get(cid) not in chairs_hit}
            if len(non_subordinate) == 1:
                resolved_note = f"resolved from {sorted(chairs_hit)} -- the others are recorded as sub-chairs of it"
                chairs_hit = {cid: people for cid, people in chairs_hit.items() if cid in non_subordinate}

        if len(chairs_hit) > 1 and len(head_chairs) == 1:
            # Several chairs mention the person, but only one page says
            # they actually head it -- e.g. Katoen heads "moves"; "ths"
            # separately says it's "embedded into" moves's chair and
            # also names him, which isn't the same claim.
            resolved_note = f"resolved from {sorted(chairs_hit)} via explicit 'headed by'/'contact' phrase"
            chairs_hit = {cid: people for cid, people in chairs_hit.items() if cid in head_chairs}

        if len(chairs_hit) == 1:
            (chair_id, people_found), = chairs_hit.items()
            entry = {
                "module_id": module_id,
                "title": title,
                "coordinator": coordinator,
                "matched_people": people_found,
                "chair_id": chair_id,
                "chair_name": chair_names[chair_id],
            }
            if resolved_note:
                entry["resolved_from_ambiguous"] = resolved_note
            matched.append(entry)
        elif len(chairs_hit) > 1:
            ambiguous.append({"module_id": module_id, "title": title, "coordinator": coordinator, "chair_candidates": chairs_hit})
        else:
            unmatched.append({"module_id": module_id, "title": title, "coordinator": coordinator, "reason": "no listed coordinator found on any scraped chair page"})

    print(f"Modules with a coordinator field: {len(rows)}")
    print(f"  not a specific person (department placeholder / N.N.): {len(not_applicable)}")
    print(f"  matched to exactly one chair: {len(matched)}")
    print(f"  ambiguous (different people/chairs for the same module): {len(ambiguous)}")
    print(f"  unmatched (real name, not found on any scraped chair page -- likely outside Informatik): {len(unmatched)}")

    resolved = [m for m in matched if m.get("resolved_from_ambiguous")]
    print(f"  of which resolved from an initial ambiguity via head/contact phrase: {len(resolved)}")

    print("\n--- sample matches (first 15) ---")
    for m in matched[:15]:
        note = f"  [{m['resolved_from_ambiguous']}]" if m.get("resolved_from_ambiguous") else ""
        print(f"  {m['title']!r} -- {m['coordinator']} -> {m['chair_id']} ({m['chair_name']}){note}")

    if ambiguous:
        print(f"\n--- ambiguous ({len(ambiguous)}) ---")
        for a in ambiguous:
            print(f"  {a['title']!r} -- {a['coordinator']} -> candidates: {a['chair_candidates']}")

    print(f"\n--- unmatched sample (first 15 of {len(unmatched)}) ---")
    for u in unmatched[:15]:
        print(f"  {u['title']!r} -- {u['coordinator']!r} ({u['reason']})")

    out_path = REPO_ROOT / "data" / "processed" / "chair_module_links_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {"matched": matched, "ambiguous": ambiguous, "unmatched": unmatched, "not_applicable": not_applicable},
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nFull report written to {out_path.relative_to(REPO_ROOT)}")

    conn = sqlite3.connect(DB_PATH)
    try:
        create_schema(conn)  # CREATE TABLE IF NOT EXISTS -- a no-op for every table except module_chairs the first time
        n_persisted = load_module_chairs(conn, str(out_path))
    finally:
        conn.close()
    print(f"Persisted {n_persisted} matched links to module_chairs in {DB_PATH.name}.")


if __name__ == "__main__":
    run()
