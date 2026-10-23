"""Runs the PO/ÜPO extractor + parser for one document and writes its
rules as JSONL.

Usage: python parse_po.py <pdf_path> <source_id> <out_path>
(write out_path under data/processed/extracted/)
"""

from __future__ import annotations

import json
import sys

from studyrag.ingestion.pdf_text import extract_text
from studyrag.ingestion.po_extract import parse_rule_block, split_into_rule_blocks


def run(pdf_path: str, source_id: str, out_path: str) -> None:
    text = extract_text(pdf_path)
    blocks = split_into_rule_blocks(text)

    records = []
    for block in blocks:
        records.extend(parse_rule_block(block, source_id))

    with open(out_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    templates = [r for r in records if r["is_template_example"]]
    cross_refs = [r for r in records if r["cross_reference"]]
    print(f"Wrote {len(records)} rule records ({len(blocks)} paragraphs) to {out_path}")
    print(f"  template/example annexes: {len(templates)}")
    print(f"  cross-document references: {len(cross_refs)}")
    for r in cross_refs:
        print(f"    § {r['paragraph']} Abs.{r['absatz']} -> {r['cross_reference']}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    run(sys.argv[1], sys.argv[2], sys.argv[3])
