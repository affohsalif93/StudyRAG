"""Loads a track definition (data/tracks/*.yaml) -- plain data,
human-reviewable without touching code.
"""

from __future__ import annotations

from pathlib import Path

import yaml

TRACKS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "tracks"


def load_track(track_id: str) -> dict:
    path = TRACKS_DIR / f"{track_id}.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def list_track_ids() -> list[str]:
    return sorted(p.stem for p in TRACKS_DIR.glob("*.yaml"))


def build_goal_graph(track_id: str) -> dict:
    """Nodes/edges connecting a track's modules to the career goal
    itself -- not prerequisites, just "this module moves you toward the
    goal", from the track YAML's own `reason` field. `kind: "goal"`
    distinguishes these from handbook-derived prerequisite edges.
    """
    track = load_track(track_id)
    goal_id = f"goal:{track_id}"
    nodes = [{"module_id": goal_id, "title": track["title"], "kind": "goal"}]
    edges = []
    for layer in ("core", "complementary", "nice_to_have"):
        for item in track.get(layer, []):
            nodes.append({"module_id": item["module_id"], "title": item["module"], "kind": "module"})
            edges.append(
                {
                    "source": item["module_id"],
                    "target": goal_id,
                    "kind": "goal",
                    "layer": layer,
                    "reason": item["reason"],
                }
            )
    return {"nodes": nodes, "edges": edges}
