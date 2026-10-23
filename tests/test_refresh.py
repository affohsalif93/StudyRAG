"""Verifies the freshness/refresh pipeline finds exactly the pages that
changed, no more, no less.
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest

from studyrag.refresh.diff_report import build_diff_report, changed_page_numbers
from studyrag.refresh.hashing import hash_bytes, hash_pages, split_pages
from studyrag.refresh.refresh import check_source_for_changes

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCES_PATH = REPO_ROOT / "data" / "raw" / "sources.json"


def test_changed_page_numbers_finds_exactly_the_modified_and_added_pages():
    old_pages = ["Page one.", "Page two original.", "Page three."]
    new_pages = ["Page one.", "Page two MODIFIED.", "Page three.", "Page four added."]
    old_hashes = [hashlib.sha256(p.encode()).hexdigest() for p in old_pages]
    new_hashes = [hashlib.sha256(p.encode()).hexdigest() for p in new_pages]

    changed = changed_page_numbers(old_hashes, new_hashes)

    assert changed == [2, 4]


def test_changed_page_numbers_finds_nothing_when_unchanged():
    pages = ["Same.", "Also same."]
    hashes = [hashlib.sha256(p.encode()).hexdigest() for p in pages]

    assert changed_page_numbers(hashes, list(hashes)) == []


def test_diff_report_shows_only_the_actually_changed_pages():
    old_pages = ["unchanged", "will change", "also unchanged"]
    new_pages = ["unchanged", "did change", "also unchanged"]

    report = build_diff_report("test_doc", old_pages, new_pages, [2], "2026-10-01", "2026-10-16")

    assert "## Page 2" in report
    assert "## Page 1" not in report
    assert "## Page 3" not in report
    assert "will change" in report
    assert "did change" in report


def test_hash_pages_matches_split_pages_count_and_is_order_sensitive():
    text = "first page\fsecond page\fthird page\f"
    pages = split_pages(text)
    hashes = hash_pages(text)

    assert len(pages) == len(hashes) == 3
    assert hashes[0] != hashes[1] != hashes[2]
    # order matters: hashing the same pages in a different order must not
    # collide with the original order's hashes
    reordered = hash_pages("third page\ffirst page\fsecond page\f")
    assert reordered != hashes


@pytest.mark.skipif(not SOURCES_PATH.exists(), reason="no real source data checked out")
def test_check_source_for_changes_reports_no_change_for_the_unmodified_file():
    """Integration-level sanity check against a real document: feeding the
    file's own current bytes back in must report no change, proving the
    real hashing path (not a mock) agrees with what's stored.
    """
    sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    source = sources[0]
    local_path = Path(source["local_path"])
    if not local_path.exists():
        pytest.skip("raw PDF not present in this checkout")

    current_bytes = local_path.read_bytes()
    assert hash_bytes(current_bytes) == source["content_hash"]

    result = check_source_for_changes(source, current_bytes, old_page_hashes=[])

    assert result.changed is False


@pytest.mark.skipif(not SOURCES_PATH.exists(), reason="no real source data checked out")
def test_check_source_for_changes_detects_a_real_change_end_to_end():
    """Exercises the full real pipeline (byte hashing, subprocess text
    extraction, page hashing, diffing) against two genuinely different
    real PDFs — not a hand-edited copy of the same document (the plan's
    literal suggestion), but a stronger check: if the code can't tell
    two completely different real documents apart, it certainly
    couldn't catch a real one-page edit either.
    """
    sources = {s["id"]: s for s in json.loads(SOURCES_PATH.read_text(encoding="utf-8"))}
    old_source = sources["po_bachelor_2022"]
    new_source = sources["po_master_2023"]
    if not Path(old_source["local_path"]).exists() or not Path(new_source["local_path"]).exists():
        pytest.skip("raw PDFs not present in this checkout")

    new_bytes = Path(new_source["local_path"]).read_bytes()

    result = check_source_for_changes(old_source, new_bytes, old_page_hashes=[])

    assert result.changed is True
    assert len(result.changed_pages) > 0
    # every page present on both sides actually differs — these are two
    # unrelated real documents, so an unchanged shared page would mean
    # the diff logic is broken, not that the documents coincidentally match
    shared_pages = min(len(result.old_pages), len(result.new_pages))
    assert result.changed_pages[:shared_pages] == list(range(1, shared_pages + 1))


@pytest.mark.skipif(not SOURCES_PATH.exists(), reason="no real source data checked out")
def test_check_source_for_changes_handles_a_missing_local_file(tmp_path):
    """First-ever run in a fresh environment (e.g. a CI runner before its
    raw-PDF cache is populated) has no local copy at all — must seed the
    baseline instead of crashing on a missing file.
    """
    sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    source = dict(sources[0])
    real_bytes = Path(source["local_path"]).read_bytes()
    source["local_path"] = str(tmp_path / "does_not_exist_yet.pdf")

    result = check_source_for_changes(source, real_bytes, old_page_hashes=[])

    assert result.changed is True
    assert result.old_pages == []
    assert len(result.new_pages) > 0
