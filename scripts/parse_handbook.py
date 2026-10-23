"""Runs the handbook extractor + parser end to end for one document and
writes both JSONL files (raw and normalized). See
studyrag-handbook-module-schema.md for the schema.

Usage:
    python parse_handbook.py <pdf_path> <source_id> <out_prefix>

Example:
    python parse_handbook.py \\
        ../data/raw/MHB_MSInf_2023_en_WiSe2026.pdf \\
        mhb_en_wise2026 \\
        ../data/processed/extracted/modules_MSInf2023_WiSe2026_en
"""

from __future__ import annotations

import json
import sys
from collections import Counter

from studyrag.ingestion.handbook_extract import (
    extract_clean_body_text,
    parse_module_block,
    split_front_matter,
    split_into_module_blocks,
)
from studyrag.ingestion.handbook_normalize import normalize_module
from studyrag.ingestion.handbook_toc import parse_toc
from studyrag.ingestion.pdf_text import extract_text


def run(pdf_path: str, source_id: str, out_prefix: str) -> None:
    raw_full_text = extract_text(pdf_path)
    full_text = extract_clean_body_text(raw_full_text)

    body_start = split_front_matter(full_text)
    toc = parse_toc(full_text[:body_start])
    spans = split_into_module_blocks(full_text, body_start)

    raw_records = [parse_module_block(span, full_text, toc, source_id) for span in spans]
    final_records = [normalize_module(r) for r in raw_records]

    raw_path = f"{out_prefix}_raw.jsonl"
    final_path = f"{out_prefix}.jsonl"

    with open(raw_path, "w", encoding="utf-8") as f:
        for r in raw_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    with open(final_path, "w", encoding="utf-8") as f:
        for r in final_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    needs_review = [r for r in raw_records if r["parse_status"] == "needs_review"]
    needs_mapping = [r for r in final_records if r["normalization_status"] == "needs_mapping"]
    toc_count = len(toc)
    body_count = len(spans)

    print(f"Wrote {len(raw_records)} raw records to {raw_path}")
    print(f"Wrote {len(final_records)} normalized records to {final_path}")
    print()
    print(f"TOC entries (unique module_id): {toc_count}")
    print(f"Body module blocks found:       {body_count}")
    if body_count != toc_count:
        print(
            f"  NOTE: counts differ by {body_count - toc_count} — check for cross-listed "
            f"modules (same module_id, two TOC entries; expected, see studyrag-decisions-log.md) "
            f"before treating this as an error."
        )
    print()
    print(f"Extractor flagged needs_review: {len(needs_review)} / {body_count}")
    for r in needs_review[:10]:
        print(f"  - {r.get('module_id')}: missing {r.get('_missing_labels')}")
    print()
    print(f"Parser flagged needs_mapping:   {len(needs_mapping)} / {body_count}")
    unmapped_counter: Counter[tuple[str, str]] = Counter()
    for r in needs_mapping:
        for u in r["unmapped_raw_values"]:
            unmapped_counter[(u["field"], u["value"])] += 1
    for (field, value), n in unmapped_counter.most_common(20):
        print(f"  - {field} = {value!r}  ({n}x)")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    run(sys.argv[1], sys.argv[2], sys.argv[3])
