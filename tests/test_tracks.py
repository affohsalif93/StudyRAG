"""build_goal_graph is pure, deterministic logic over a real track YAML
file (no DB, no LLM), unit-tested directly here.
"""

from __future__ import annotations

from studyrag.recommender.tracks import build_goal_graph


def test_goal_node_present_and_titled():
    graph = build_goal_graph("software_engineering")
    goal_nodes = [n for n in graph["nodes"] if n["kind"] == "goal"]
    assert len(goal_nodes) == 1
    assert goal_nodes[0]["module_id"] == "goal:software_engineering"
    assert goal_nodes[0]["title"] == "Software engineer"


def test_every_track_module_gets_a_goal_edge():
    graph = build_goal_graph("software_engineering")
    edge_sources = {e["source"] for e in graph["edges"]}
    module_nodes = [n for n in graph["nodes"] if n["kind"] == "module"]
    assert edge_sources == {n["module_id"] for n in module_nodes}
    assert all(e["target"] == "goal:software_engineering" and e["kind"] == "goal" for e in graph["edges"])
    assert all(e["layer"] in ("core", "complementary", "nice_to_have") for e in graph["edges"])
    assert all(e["reason"] for e in graph["edges"])
