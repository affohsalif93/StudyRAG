"""Re-fetches each source, compares against its stored hash, and -- on
a real change -- archives the old version (raw PDF + extracted JSONL)
before overwriting, so history is kept on disk even though the live
DB/index stay wipe-and-reload.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import requests

from studyrag.refresh.hashing import hash_bytes, hash_pages, split_pages
from studyrag.ingestion.pdf_text import extract_text


@dataclass
class ChangeResult:
    source_id: str
    changed: bool
    old_doc_hash: str
    new_doc_hash: str
    changed_pages: list[int] = field(default_factory=list)
    old_pages: list[str] = field(default_factory=list)
    new_pages: list[str] = field(default_factory=list)
    new_page_hashes: list[str] = field(default_factory=list)
    new_bytes: bytes = b""


def fetch_source_bytes(url: str, timeout: int = 30) -> bytes:
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.content


def check_source_for_changes(source: dict, new_bytes: bytes, old_page_hashes: list[str]) -> ChangeResult:
    """Compares the freshly fetched bytes against the source's stored
    document hash and page hashes. Only re-extracts page text for a
    document that actually changed — no point paying for text extraction
    on every source every time nothing changed.

    A missing local file (first-ever run in a fresh environment) is
    treated as "no prior version to diff against," not a change:
    old_pages is empty and every new page is reported as the diff
    (seeding the baseline) rather than crashing.
    """
    new_doc_hash = hash_bytes(new_bytes)
    old_doc_hash = source["content_hash"]

    if new_doc_hash == old_doc_hash and Path(source["local_path"]).exists():
        return ChangeResult(source_id=source["id"], changed=False, old_doc_hash=old_doc_hash, new_doc_hash=new_doc_hash)

    if Path(source["local_path"]).exists():
        old_text = extract_text(source["local_path"])
        old_pages = split_pages(old_text)
    else:
        old_pages = []

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(new_bytes)
        tmp_path = tmp.name
    try:
        new_text = extract_text(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    new_pages = split_pages(new_text)
    new_page_hashes = hash_pages(new_text)

    changed_pages = [
        i + 1
        for i in range(max(len(old_page_hashes), len(new_page_hashes)))
        if (old_page_hashes[i] if i < len(old_page_hashes) else None)
        != (new_page_hashes[i] if i < len(new_page_hashes) else None)
    ]

    return ChangeResult(
        source_id=source["id"],
        changed=True,
        old_doc_hash=old_doc_hash,
        new_doc_hash=new_doc_hash,
        changed_pages=changed_pages,
        old_pages=old_pages,
        new_pages=new_pages,
        new_page_hashes=new_page_hashes,
        new_bytes=new_bytes,
    )


def archive_old_version(source: dict, extracted_dir: Path, archive_root: Path) -> None:
    """Copies the old raw PDF and any extracted JSONL file(s) belonging
    to this source into a retrieved_at-stamped archive directory, before
    either gets overwritten by the new version.
    """
    stamp = source["retrieved_at"]
    dest_dir = archive_root / f"{source['id']}_{stamp}"
    dest_dir.mkdir(parents=True, exist_ok=True)

    local_path = Path(source["local_path"])
    if local_path.exists():
        shutil.copy2(local_path, dest_dir / local_path.name)

    for jsonl_path in extracted_dir.glob(f"*{source['id']}*"):
        shutil.copy2(jsonl_path, dest_dir / jsonl_path.name)


def apply_new_version(source: dict, new_bytes: bytes, new_retrieved_at: str) -> dict:
    """Overwrites the local PDF with the new bytes and returns an updated
    copy of the source's sources.json entry. `version` is deliberately
    left untouched — the human-readable regulation version string isn't
    reliably derivable from the PDF bytes, so it stays a manual edit.
    """
    Path(source["local_path"]).write_bytes(new_bytes)
    updated = dict(source)
    updated["content_hash"] = hash_bytes(new_bytes)
    updated["retrieved_at"] = new_retrieved_at
    return updated


def load_page_hashes(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_page_hashes(path: Path, page_hashes: dict[str, list[str]]) -> None:
    path.write_text(json.dumps(page_hashes, ensure_ascii=False, indent=2), encoding="utf-8")


def save_sources(path: Path, sources: list[dict]) -> None:
    path.write_text(json.dumps(sources, ensure_ascii=False, indent=2), encoding="utf-8")
