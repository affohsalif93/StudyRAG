"""The deterministic half of chair lookup -- registry loading and
robots.txt handling -- tested independent of the agent's own
LLM-driven behavior.
"""

from __future__ import annotations

from studyrag.chair_lookup.tools import extract_readable_text, load_chairs, robots_allows


def test_load_chairs_returns_every_registered_chair():
    chairs = load_chairs()
    assert len(chairs) >= 40
    ids = [c["id"] for c in chairs]
    assert len(ids) == len(set(ids))  # no duplicate ids


def test_load_chairs_includes_a_known_entry_with_no_url():
    chairs = {c["id"]: c for c in load_chairs()}
    assert chairs["cps-rwth"]["url"] is None


def test_extract_readable_text_strips_script_and_style():
    html = "<html><body><script>evil()</script><style>.x{}</style><p>Real content here.</p></body></html>"
    text = extract_readable_text(html)
    assert "evil" not in text
    assert "Real content here." in text


def test_robots_allows_a_real_permissive_site():
    assert robots_allows("https://www.lics.rwth-aachen.de/") is True


def test_robots_allows_fails_safe_on_unreachable_host():
    assert robots_allows("https://this-domain-does-not-exist-studyrag-test.invalid/page") is False
