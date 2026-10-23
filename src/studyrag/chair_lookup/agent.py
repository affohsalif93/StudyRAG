"""The chair-lookup agent — the one place in StudyRAG where a model is
handed tools and decides how to use them, rather than a fixed pipeline.
Chair info is dynamic and chair-specific, so a static indexed corpus
can't cover it and there's no grounding guarantee to protect here.

Uses LangGraph long-term memory: the model can remember/forget durable
facts about the current student (career goal, weak subjects) via tool
calls, backed by a SQLite store so it persists across CLI invocations.
"""

from __future__ import annotations

from dataclasses import dataclass

from langchain.agents import create_agent

from studyrag.answering.prompts import load_prompt
from studyrag.chair_lookup.tools import fetch_chair_page, find_thesis_info, list_chairs
from studyrag.config import CHAT_MODEL, DEFAULT_USER_ID
from studyrag.memory.store import SQLiteMemoryStore
from studyrag.memory.tools import forget, load_memory, remember

_tools = [list_chairs, fetch_chair_page, find_thesis_info, remember, forget]

try:
    from langchain_tavily import TavilySearch

    _tools.append(TavilySearch(max_results=5))
except Exception:
    # No TAVILY_API_KEY configured yet — the agent still works with just
    # the chair-registry tools, it just can't self-heal a dead URL by
    # searching for a replacement. See studyrag-decisions-log.md.
    pass

_store = SQLiteMemoryStore()


@dataclass
class ChairAgentContext:
    user_id: str


def build_chair_agent(system_prompt: str):
    return create_agent(
        model=f"openai:{CHAT_MODEL}",
        tools=_tools,
        system_prompt=system_prompt,
        store=_store,
        context_schema=ChairAgentContext,
    )


def _build_system_prompt(user_id: str) -> str:
    base_prompt = load_prompt("chair_agent_system_prompt")
    memory = load_memory(_store, user_id)
    if not memory:
        return base_prompt
    known_facts = "\n".join(f"- {key}: {value}" for key, value in memory.items())
    return f"{base_prompt}\n\n## What you already know about this student\n{known_facts}"


def ask_chair_agent(question: str, user_id: str = DEFAULT_USER_ID) -> str:
    agent = build_chair_agent(_build_system_prompt(user_id))
    result = agent.invoke(
        {"messages": [{"role": "user", "content": question}]},
        context=ChairAgentContext(user_id=user_id),
    )
    content = result["messages"][-1].content

    # gpt-6-luna (a reasoning model) returns a list of typed content
    # blocks (reasoning + text), not a plain string — found by running
    # this for real: the raw content included an opaque encrypted
    # reasoning blob that must never be surfaced as the answer.
    if isinstance(content, str):
        return content
    text_parts = [block["text"] for block in content if isinstance(block, dict) and block.get("type") == "text"]
    return "\n".join(text_parts)
