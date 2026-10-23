"""Builds the combined retrieval index: module chunks + operative
PO/ÜPO rule chunks, embedded with OpenAI into one store --
data/processed/embeddings/chunk_index.npz + .meta.json. One combined
index, not two separate ones. Requires OPENAI_API_KEY.

Usage: python build_module_index.py
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from dotenv import load_dotenv

from studyrag.retrieval.chunks import build_module_chunks, build_rule_chunks
from studyrag.retrieval.embed import build_index

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "studyrag.db"
OUT_PATH = REPO_ROOT / "data" / "processed" / "embeddings" / "chunk_index.npz"


def main() -> None:
    load_dotenv(REPO_ROOT / ".env")

    conn = sqlite3.connect(DB_PATH)
    module_chunks = build_module_chunks(conn)
    rule_chunks = build_rule_chunks(conn)
    conn.close()

    chunks = module_chunks + rule_chunks
    print(f"Built {len(module_chunks)} module chunks + {len(rule_chunks)} rule chunks = {len(chunks)} total.")

    print(f"Embedding with OpenAI ({OUT_PATH.name})... this calls the API.")
    build_index(chunks, str(OUT_PATH))
    print(f"Wrote {OUT_PATH} and {OUT_PATH.with_suffix('').with_suffix('.meta.json')}")


if __name__ == "__main__":
    main()
