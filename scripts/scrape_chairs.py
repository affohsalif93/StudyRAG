"""Fetches real page content for every chair in data/raw/chairs.json.
Reuses chair_lookup/tools.py's robots_allows()/extract_readable_text()/
_USER_AGENT directly rather than reimplementing them -- the project's
one audited scraping path.

Unlike fetch_chair_page() (a live, per-query RAG fallback truncated to
8000 chars), this stores the full extracted text permanently to
data/raw/chairs/<id>.txt, for later chair-module linking. Every outcome
(ok, no URL on file, robots disallows it, the fetch errors, nothing
readable came back) is recorded in last_fetch_status rather than
silently skipped.

Usage: python scripts/scrape_chairs.py (run from the repo root)
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from studyrag.chair_lookup.tools import _USER_AGENT, extract_readable_text, robots_allows  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
CHAIRS_PATH = REPO_ROOT / "data" / "raw" / "chairs.json"
CONTENT_DIR = REPO_ROOT / "data" / "raw" / "chairs"
REQUEST_DELAY_SECONDS = 1.5  # polite rate limit across ~42 requests, mostly to RWTH's own domains


def fetch_one(chair: dict) -> dict:
    """Returns the updated chair dict. Never raises -- every outcome is
    recorded in last_fetch_status instead of stopping the whole run.
    """
    url = chair.get("url")

    if not url:
        return {**chair, "last_fetch_status": "no_url"}

    if not robots_allows(url):
        print("  robots.txt disallows this URL -- skipping.")
        return {**chair, "last_fetch_status": "disallowed_by_robots"}

    try:
        response = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"  fetch failed: {e}")
        return {**chair, "last_fetch_status": f"error: {e}"}

    text = extract_readable_text(response.text)
    if not text.strip():
        print("  fetched but no readable text extracted (JS-rendered page?).")
        return {**chair, "last_fetch_status": "empty_content"}

    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    local_path = CONTENT_DIR / f"{chair['id']}.txt"
    local_path.write_text(text, encoding="utf-8")

    return {
        **chair,
        "content_hash": content_hash,
        "last_fetch_status": "ok",
        "local_path": str(local_path.relative_to(REPO_ROOT)).replace("\\", "/"),
        "content_retrieved_at": dt.date.today().isoformat(),
    }


def run() -> None:
    chairs = json.loads(CHAIRS_PATH.read_text(encoding="utf-8"))
    updated = []
    counts: dict[str, int] = defaultdict(int)

    for i, chair in enumerate(chairs):
        print(f"[{i + 1}/{len(chairs)}] {chair['id']} ({chair['group_type']}) -- {chair.get('url') or 'NO URL'}")
        result = fetch_one(chair)
        status = result["last_fetch_status"]
        counts["error" if status.startswith("error:") else status] += 1
        updated.append(result)
        if chair.get("url"):
            time.sleep(REQUEST_DELAY_SECONDS)

    CHAIRS_PATH.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("\nDone.")
    for status, n in sorted(counts.items()):
        print(f"  {status}: {n}")

    failed = [c["id"] for c in updated if c["last_fetch_status"] != "ok"]
    if failed:
        print(f"\nNeeds manual review ({len(failed)}): {', '.join(failed)}")


if __name__ == "__main__":
    run()
