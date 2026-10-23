"""Tools that let a tool-calling agent write to its own long-term memory
about the current user. The model decides *when* to remember or forget
something, steered by its system prompt — but *who* it's writing about
is bound by the calling code via LangGraph's runtime context
(`get_runtime().context.user_id`), never a tool argument the model
could supply itself. A `user_id` parameter on the tool would let the
model write to the wrong user's memory by mistake or hallucination.
"""

from __future__ import annotations

from langchain_core.tools import tool
from langgraph.runtime import get_runtime
from langgraph.store.base import BaseStore

NAMESPACE_PREFIX = "user_memory"


def _namespace(user_id: str) -> tuple[str, str]:
    return (NAMESPACE_PREFIX, user_id)


def write_memory(store: BaseStore, user_id: str, key: str, value: str) -> None:
    """The actual write — plain function, no LangGraph runtime required,
    so both the chair agent's `remember` tool (below) and the core fixed
    pipeline (src/studyrag/answering/chat.py, which isn't a tool-calling
    agent and has no Runtime to pull a store/user_id from) can write
    through the same path instead of duplicating this logic.
    """
    store.put(_namespace(user_id), key, {"text": value})


def delete_memory(store: BaseStore, user_id: str, key: str) -> None:
    store.delete(_namespace(user_id), key)


@tool
def remember(key: str, value: str) -> str:
    """Saves or updates one durable fact about the current student,
    under a short descriptive key (e.g. "career_goal", "weak_subjects",
    "modules_completed"). You'll be shown what's already remembered
    before each conversation — reuse the same key for a fact that
    changes (the student corrects or updates something they said
    before) rather than inventing a new key, which would leave a stale
    duplicate instead of a clean update."""
    runtime = get_runtime()
    write_memory(runtime.store, runtime.context.user_id, key, value)
    return f"Remembered: {key} = {value}"


@tool
def forget(key: str) -> str:
    """Deletes one previously remembered fact about the current student
    by its key. Use this when a fact is no longer true and shouldn't be
    replaced by anything else, not just updated."""
    runtime = get_runtime()
    delete_memory(runtime.store, runtime.context.user_id, key)
    return f"Forgot: {key}"


def load_memory(store: BaseStore, user_id: str) -> dict[str, str]:
    """Not a tool — called by the orchestrating code before invoking the
    agent, to inject what's already known into the system prompt. This
    way the model doesn't need a tool call just to see its own memory,
    and can see existing keys before deciding whether to update one
    rather than risk creating a near-duplicate under a slightly
    different name.
    """
    items = store.search(_namespace(user_id))
    return {item.key: item.value["text"] for item in items}
