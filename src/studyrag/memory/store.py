"""LangGraph long-term memory, backed by SQLite rather than Postgres (no
Postgres dependency anywhere else in this project) or LangGraph's own
`InMemoryStore` — which would not survive between separate CLI process
invocations, this project's actual usage pattern (`python -m
studyrag.ask "..."` starts a fresh process every time). Verified before
building: `langgraph.store` only ships `base` and `memory` backends, no
SQLite one, via `pkgutil.iter_modules`.

Implements only what `BaseStore` actually requires — `batch`/`abatch`
are its only abstract methods (checked via `BaseStore.__abstractmethods__`,
not assumed); `get`/`put`/`delete`/`search`/`list_namespaces` are
convenience wrappers `BaseStore` already builds on top of them.

Deliberately its own file, not a table in `data/studyrag.db`: that
database is fully derived and explicitly safe to delete and rebuild
from scratch at any time (see studyrag-decisions-log.md) — mixing
permanent personal memory into it would make that no longer true.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from langgraph.store.base import GetOp, Item, ListNamespacesOp, Op, PutOp, Result, SearchItem, SearchOp
from langgraph.store.base import BaseStore as _BaseStore

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_DB_PATH = REPO_ROOT / "data" / "user_memory.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory (
    namespace TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (namespace, key)
);
"""


def _ns_to_str(namespace: tuple[str, ...]) -> str:
    return "/".join(namespace)


def _ns_from_str(s: str) -> tuple[str, ...]:
    return tuple(s.split("/")) if s else ()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SQLiteMemoryStore(_BaseStore):
    """A minimal, synchronous BaseStore: no vector/semantic search (not
    needed here — this project only ever does exact key lookups or lists
    a user's whole namespace), no TTL. Opens its own connection per
    batch call rather than holding one open across the store's
    lifetime, matching this project's existing "open, use, close"
    sqlite3 convention elsewhere.
    """

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH):
        self.db_path = str(db_path)
        conn = sqlite3.connect(self.db_path)
        conn.executescript(_SCHEMA)
        conn.commit()
        conn.close()

    def batch(self, ops: list[Op]) -> list[Result]:
        conn = sqlite3.connect(self.db_path)
        try:
            results = [self._run_op(conn, op) for op in ops]
            conn.commit()
            return results
        finally:
            conn.close()

    async def abatch(self, ops: list[Op]) -> list[Result]:
        return self.batch(ops)

    def _run_op(self, conn: sqlite3.Connection, op: Op) -> Result:
        if isinstance(op, GetOp):
            return self._get(conn, op)
        if isinstance(op, PutOp):
            return self._put(conn, op)
        if isinstance(op, SearchOp):
            return self._search(conn, op)
        if isinstance(op, ListNamespacesOp):
            return self._list_namespaces(conn, op)
        raise TypeError(f"Unsupported op: {op!r}")

    def _get(self, conn: sqlite3.Connection, op: GetOp) -> Item | None:
        row = conn.execute(
            "SELECT value, created_at, updated_at FROM memory WHERE namespace = ? AND key = ?",
            (_ns_to_str(op.namespace), op.key),
        ).fetchone()
        if row is None:
            return None
        value, created_at, updated_at = row
        return Item(
            value=json.loads(value),
            key=op.key,
            namespace=op.namespace,
            created_at=datetime.fromisoformat(created_at),
            updated_at=datetime.fromisoformat(updated_at),
        )

    def _put(self, conn: sqlite3.Connection, op: PutOp) -> None:
        namespace = _ns_to_str(op.namespace)
        if op.value is None:
            conn.execute("DELETE FROM memory WHERE namespace = ? AND key = ?", (namespace, op.key))
            return
        now = _now()
        existing = conn.execute(
            "SELECT created_at FROM memory WHERE namespace = ? AND key = ?", (namespace, op.key)
        ).fetchone()
        created_at = existing[0] if existing else now
        conn.execute(
            """
            INSERT INTO memory (namespace, key, value, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(namespace, key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (namespace, op.key, json.dumps(op.value, ensure_ascii=False), created_at, now),
        )
        return None

    def _search(self, conn: sqlite3.Connection, op: SearchOp) -> list[SearchItem]:
        prefix = _ns_to_str(op.namespace_prefix)
        rows = conn.execute(
            "SELECT namespace, key, value, created_at, updated_at FROM memory "
            "WHERE namespace = ? OR namespace LIKE ? ORDER BY key LIMIT ? OFFSET ?",
            (prefix, f"{prefix}/%", op.limit, op.offset),
        ).fetchall()
        items = []
        for namespace, key, value, created_at, updated_at in rows:
            parsed = json.loads(value)
            if op.filter and not all(parsed.get(k) == v for k, v in op.filter.items()):
                continue
            items.append(
                SearchItem(
                    namespace=_ns_from_str(namespace),
                    key=key,
                    value=parsed,
                    created_at=datetime.fromisoformat(created_at),
                    updated_at=datetime.fromisoformat(updated_at),
                    score=None,
                )
            )
        return items

    def _list_namespaces(self, conn: sqlite3.Connection, op: ListNamespacesOp) -> list[tuple[str, ...]]:
        rows = conn.execute("SELECT DISTINCT namespace FROM memory").fetchall()
        namespaces = {_ns_from_str(r[0]) for r in rows}
        if op.prefix:
            namespaces = {n for n in namespaces if n[: len(op.prefix)] == tuple(op.prefix)}
        if op.suffix:
            namespaces = {n for n in namespaces if n[-len(op.suffix) :] == tuple(op.suffix)}
        ordered = sorted(namespaces)
        return ordered[op.offset : op.offset + op.limit]
