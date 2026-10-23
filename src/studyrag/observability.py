"""The one place an OpenAI client gets created. Returns a LangSmith-traced
client when LANGSMITH_TRACING is on, a plain one otherwise -- every call
site already does `client = client or get_openai_client()`, so tracing is
opt-in with zero behavior change when no LANGSMITH_API_KEY is set.
"""

from __future__ import annotations

import os

from langsmith.wrappers import wrap_openai
from openai import OpenAI


def get_openai_client() -> OpenAI:
    client = OpenAI()
    if os.environ.get("LANGSMITH_TRACING", "").lower() == "true":
        client = wrap_openai(client)
    return client
