"""Spot-checks the real database against the source PDFs. See
src/studyrag/db/validate.py for the actual checks.

Usage: python validate_db.py [seed]
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from studyrag.db.validate import check_early_master_cap, check_random_modules

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "data" / "studyrag.db"


def main() -> None:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else None
    conn = sqlite3.connect(DB_PATH)
    try:
        failures = check_random_modules(conn, REPO_ROOT, 10, seed) + check_early_master_cap(conn)
    finally:
        conn.close()

    if failures:
        print(f"\n{len(failures)} FAILURE(S):")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
