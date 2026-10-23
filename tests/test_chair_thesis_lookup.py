"""The parts of find_thesis_info that don't need a real network fetch
are pure, deterministic logic, unit-tested here. The tool itself (a
live fetch against a real chair site) is exercised against real chairs
instead.
"""

from __future__ import annotations

from studyrag.chair_lookup.tools import _find_thesis_contact_email, _find_thesis_links


def test_find_thesis_links_matches_real_keyword_text():
    html = """
    <html><body>
      <a href="/BScMSc.de.shtml">Abschlussarbeiten</a>
      <a href="/team.shtml">Team</a>
      <a href="/theses/guidelines">thesis guidelines</a>
    </body></html>
    """
    links = _find_thesis_links(html, "https://example.rwth-aachen.de/index.shtml")
    urls = {link["url"] for link in links}
    assert "https://example.rwth-aachen.de/BScMSc.de.shtml" in urls
    assert "https://example.rwth-aachen.de/theses/guidelines" in urls
    assert not any("team" in url for url in urls)


def test_find_thesis_links_excludes_mailto_and_tel():
    html = """
    <html><body>
      <a href="mailto:thesis@example.de">thesis@example.de</a>
      <a href="tel:+4912345">Call about your thesis</a>
      <a href="/real-thesis-page">Thesis page</a>
    </body></html>
    """
    links = _find_thesis_links(html, "https://example.de/")
    assert len(links) == 1
    assert links[0]["url"] == "https://example.de/real-thesis-page"


def test_find_thesis_contact_email_requires_proximity_to_keyword():
    text = "Contact us at office@example.de. For thesis inquiries, write to thesis@example.de instead."
    assert _find_thesis_contact_email(text) == "thesis@example.de"


def test_find_thesis_contact_email_returns_none_when_absent():
    text = "We publish regularly at top venues. Contact office@example.de for general questions."
    assert _find_thesis_contact_email(text) is None
