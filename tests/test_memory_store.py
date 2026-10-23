"""LangGraph long-term memory: verifies the custom SQLite-backed
BaseStore implements real CRUD semantics and namespace isolation, and
genuinely persists across separate process invocations — the property
that ruled out LangGraph's own InMemoryStore for this project (see
studyrag-decisions-log.md).
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from studyrag.memory.store import SQLiteMemoryStore


@pytest.fixture
def store(tmp_path):
    return SQLiteMemoryStore(tmp_path / "test_memory.db")


def test_put_then_get(store):
    store.put(("user_memory", "alice"), "career_goal", {"text": "machine learning engineer"})
    item = store.get(("user_memory", "alice"), "career_goal")
    assert item.value == {"text": "machine learning engineer"}


def test_put_with_same_key_overwrites_not_duplicates(store):
    store.put(("user_memory", "alice"), "career_goal", {"text": "machine learning engineer"})
    store.put(("user_memory", "alice"), "career_goal", {"text": "research scientist"})
    item = store.get(("user_memory", "alice"), "career_goal")
    assert item.value == {"text": "research scientist"}
    assert len(store.search(("user_memory", "alice"))) == 1


def test_delete_removes_the_item(store):
    store.put(("user_memory", "alice"), "weak_subjects", {"text": "linear algebra"})
    store.delete(("user_memory", "alice"), "weak_subjects")
    assert store.get(("user_memory", "alice"), "weak_subjects") is None


def test_search_scopes_to_namespace_only(store):
    store.put(("user_memory", "alice"), "career_goal", {"text": "x"})
    store.put(("user_memory", "bob"), "career_goal", {"text": "y"})
    alice_items = store.search(("user_memory", "alice"))
    assert len(alice_items) == 1
    assert alice_items[0].value == {"text": "x"}


def test_get_missing_key_returns_none(store):
    assert store.get(("user_memory", "alice"), "nonexistent") is None


def test_persists_across_separate_processes(tmp_path):
    db_path = tmp_path / "persist_test.db"
    write_script = f"""
from studyrag.memory.store import SQLiteMemoryStore
store = SQLiteMemoryStore({str(db_path)!r})
store.put(('user_memory', 'alice'), 'career_goal', {{'text': 'machine learning engineer'}})
"""
    read_script = f"""
from studyrag.memory.store import SQLiteMemoryStore
store = SQLiteMemoryStore({str(db_path)!r})
item = store.get(('user_memory', 'alice'), 'career_goal')
print(item.value['text'] if item else 'MISSING')
"""
    subprocess.run([sys.executable, "-c", write_script], check=True)
    result = subprocess.run([sys.executable, "-c", read_script], check=True, capture_output=True, text=True)
    assert result.stdout.strip() == "machine learning engineer"
