"""Tools for a tool-calling agent to look up information from chair
websites. Chair info (offering history, current contacts, thesis
topics) is dynamic and chair-specific -- a static indexed corpus can't
cover it, so there's nothing to index here; a model deciding which
chair, what to fetch, and whether the result answers the question is
the right shape for this one case.

Everything here answers honestly when it can't: a blocked page, a
missing URL, or a dead link returns a clear ERROR string the model can
read and relay, never a guess dressed up as fact.
"""

from __future__ import annotations

import json
import re
import urllib.robotparser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from langchain_core.tools import tool

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CHAIRS_PATH = REPO_ROOT / "data" / "raw" / "chairs.json"

_USER_AGENT = "StudyRAG-bot/0.1 (student project, non-commercial; contact via github repo)"
_MAX_PAGE_CHARS = 8000  # this is a fallback lookup, not the primary indexed corpus

# German and English thesis-related terms. A chair's landing page almost
# never lists topics itself -- usually just a nav link to a separate
# "Abschlussarbeiten" page, or occasionally a thesis contact email.
_THESIS_KEYWORDS = re.compile(r"abschlussarbeit|bachelorarbeit|masterarbeit|thesis", re.IGNORECASE)
_EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def load_chairs() -> list[dict]:
    return json.loads(CHAIRS_PATH.read_text(encoding="utf-8"))


def robots_allows(url: str) -> bool:
    """Respects robots.txt before fetching anything. Fails safe — if
    robots.txt itself can't be read, treat the page as not allowed.
    """
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(robots_url)
    try:
        parser.read()
    except Exception:
        return False
    return parser.can_fetch(_USER_AGENT, url)


def extract_readable_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return " ".join(soup.get_text(separator=" ").split())


@tool
def list_chairs() -> str:
    """Lists every CS chair/research group at RWTH Aachen with its id,
    name, and website, so you can pick the one relevant to the
    student's question before fetching its page. `sub-chair of <id>`
    is a real, verified relationship (found by reading the chair's own
    page, not guessed from its Informatik number) -- check that parent
    or child too if the first chair you try doesn't have the answer."""
    chairs = load_chairs()
    lines = []
    for c in chairs:
        parent_note = f", sub-chair of {c['parent_chair_id']}" if c.get("parent_chair_id") else ""
        lines.append(f"{c['id']}: {c['name']} (Informatik {c['informatik_number']}, {c['group_type']}{parent_note}) - {c['url'] or 'NO URL ON FILE'}")
    return "\n".join(lines)


@tool
def fetch_chair_page(chair_id: str) -> str:
    """Fetches and returns the readable text of one chair's website,
    identified by its id from list_chairs. Respects robots.txt. Returns
    a clear ERROR string (never silently empty or fabricated) if the
    chair id is unknown, no URL is on file, robots.txt disallows it, or
    the fetch fails — in any of those cases, try search_web instead."""
    chairs = {c["id"]: c for c in load_chairs()}
    chair = chairs.get(chair_id)
    if chair is None:
        return f"ERROR: no chair with id {chair_id!r}. Call list_chairs first to see valid ids."
    if not chair["url"]:
        return f"ERROR: no URL on file for {chair['name']} (Informatik {chair['informatik_number']}). Try search_web."

    url = chair["url"]
    if not robots_allows(url):
        return f"ERROR: robots.txt disallows fetching {url}."

    try:
        response = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        return f"ERROR: could not fetch {url}: {e}. The URL may be outdated — try search_web to find a current one."

    text = extract_readable_text(response.text)
    return text[:_MAX_PAGE_CHARS]


def _find_thesis_links(html: str, base_url: str) -> list[dict]:
    """Real <a> links on a chair's page whose visible text names a
    thesis/final-project page -- never a guessed URL pattern, since
    chair sites don't share one."""
    soup = BeautifulSoup(html, "html.parser")
    seen_urls: set[str] = set()
    links: list[dict] = []
    for a in soup.find_all("a", href=True):
        link_text = a.get_text(strip=True)
        href = a["href"]
        if not link_text or not _THESIS_KEYWORDS.search(link_text):
            continue
        if href.startswith(("mailto:", "tel:", "javascript:")):
            continue  # not a fetchable page -- an email here is already caught by _find_thesis_contact_email
        url = urljoin(base_url, href)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        links.append({"text": link_text, "url": url})
    return links


def _find_thesis_contact_email(text: str) -> str | None:
    """An email address appearing shortly after a thesis-related keyword
    on the page itself. Forward-only on purpose -- a backward window
    picked up unrelated, earlier emails that just happened to sit within
    range of the keyword.
    """
    for m in _THESIS_KEYWORDS.finditer(text):
        window = text[m.start() : m.start() + 100]
        email_match = _EMAIL_PATTERN.search(window)
        if email_match:
            return email_match.group(0)
    return None


@tool
def find_thesis_info(chair_id: str) -> str:
    """Looks for thesis/final-project information on a chair's own
    website: a thesis-specific contact email mentioned directly on its
    main page, and/or a linked thesis/Abschlussarbeiten page (fetched
    too, respecting robots.txt again). Most chair landing pages only
    link to a separate thesis page rather than listing topics
    themselves -- call this before assuming a chair has no thesis
    information at all. Returns a clear statement that nothing was
    found if that's the real outcome -- never guesses a URL pattern or
    invents a contact."""
    chairs = {c["id"]: c for c in load_chairs()}
    chair = chairs.get(chair_id)
    if chair is None:
        return f"ERROR: no chair with id {chair_id!r}. Call list_chairs first to see valid ids."
    if not chair["url"]:
        return f"ERROR: no URL on file for {chair['name']} (Informatik {chair['informatik_number']}). Try search_web."

    url = chair["url"]
    if not robots_allows(url):
        return f"ERROR: robots.txt disallows fetching {url}."

    try:
        response = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        return f"ERROR: could not fetch {url}: {e}. The URL may be outdated — try search_web to find a current one."

    main_text = extract_readable_text(response.text)
    contact_email = _find_thesis_contact_email(main_text)
    links = _find_thesis_links(response.text, url)

    parts = []
    if contact_email:
        parts.append(f"Thesis contact email found directly on {chair['name']}'s page: {contact_email}")

    if links:
        link = links[0]
        if not robots_allows(link["url"]):
            parts.append(f"Found a thesis-related link ({link['text']!r}, {link['url']}) but robots.txt disallows fetching it.")
        else:
            try:
                sub_response = requests.get(link["url"], headers={"User-Agent": _USER_AGENT}, timeout=15)
                sub_response.raise_for_status()
                sub_text = extract_readable_text(sub_response.text)[:_MAX_PAGE_CHARS]
                parts.append(f"Thesis page linked as {link['text']!r} ({link['url']}):\n{sub_text}")
            except requests.RequestException as e:
                parts.append(f"Found a thesis-related link ({link['url']}) but could not fetch it: {e}")
        if len(links) > 1:
            others = ", ".join(f"{l['text']!r} ({l['url']})" for l in links[1:])
            parts.append(f"Other thesis-related links on this page, not fetched: {others}")

    if not parts:
        return f"No thesis-related link or contact email found on {chair['name']}'s own landing page ({url}). It may be reachable only from a page this chair's site links to from elsewhere — try search_web."

    return "\n\n".join(parts)
