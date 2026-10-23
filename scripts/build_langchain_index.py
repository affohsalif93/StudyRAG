"""Builds the LangChain (Chroma) vector store, parallel to
scripts/build_chunk_index.py's NumPy one -- same chunks, same source
data, different mechanics, for comparing the LangChain pipeline against
the bare-pipeline baseline. Requires OPENAI_API_KEY.

Usage: python build_langchain_index.py
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from dotenv import load_dotenv

from studyrag.langchain_pipeline.vectorstore import build_vectorstore

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "studyrag.db"
PERSIST_DIR = REPO_ROOT / "data" / "processed" / "embeddings" / "langchain_chroma"


def main() -> None:
    load_dotenv(REPO_ROOT / ".env")

    conn = sqlite3.connect(DB_PATH)
    print("Building the Chroma vector store... this calls the OpenAI embeddings API.")
    vectorstore = build_vectorstore(conn, str(PERSIST_DIR))
    conn.close()

    count = vectorstore._collection.count()
    print(f"Wrote {count} embedded documents to {PERSIST_DIR}")


if __name__ == "__main__":
    main()
