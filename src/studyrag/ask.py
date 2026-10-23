"""CLI: python -m studyrag.ask "your question"

Prints the grounded answer (disclaimer already included) and the
sources it was actually built from.
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

from studyrag.answering.chat import answer_question
from studyrag.retrieval.embed import load_index

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
INDEX_PATH = REPO_ROOT / "data" / "processed" / "embeddings" / "chunk_index.npz"


def main() -> None:
    if len(sys.argv) < 2:
        print('Usage: python -m studyrag.ask "your question"')
        sys.exit(1)
    question = " ".join(sys.argv[1:])

    load_dotenv(REPO_ROOT / ".env")
    vectors, metadata = load_index(str(INDEX_PATH))
    result = answer_question(question, vectors, metadata, k=5)

    print(result["answer"])
    print()
    print("Sources:")
    for i, s in enumerate(result["sources"], 1):
        print(f"  [{i}] ({s['kind']}) {s['title']}")


if __name__ == "__main__":
    main()
