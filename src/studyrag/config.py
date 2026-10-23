"""One place that names which LLM/embedding model/provider is in use, so
swapping either is a one-line change here, not a hunt through every call
site.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Every entry point (api/app.py's lifespan, ask.py's main(), the eval
# scripts) also calls load_dotenv() itself, but only inside a function
# body -- by the time that runs, this module has already been imported
# (pulled in transitively by something imported at that file's top
# level) and every os.environ.get() below has already executed against
# whatever the OS environment had at process start, .env or not. Loading
# it here, at this module's own import time, is what actually makes a
# .env-only override (e.g. STUDYRAG_NEO4J_URI) take effect anywhere.
load_dotenv(REPO_ROOT / ".env")

DB_PATH = REPO_ROOT / "data" / "studyrag.db"

# The elective recommender's prerequisite graph. Neo4j, not a SQLite
# table -- a deliberate choice despite this project's otherwise
# SQLite-everywhere pattern (see studyrag-decisions-log.md). Local dev
# default matches `docker compose up`'s own default password.
NEO4J_URI = os.environ.get("STUDYRAG_NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("STUDYRAG_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("STUDYRAG_NEO4J_PASSWORD", "studyrag_dev_password")

# StudyRAG is currently a single-user personal tool -- one fixed default
# user id, not a real identity system, so repeated CLI calls accumulate
# the same memory instead of each starting fresh. The parameter exists on
# every function that takes a user_id so a future multi-user interface
# can pass a real one per request without a signature change.
DEFAULT_USER_ID = "default_user"

# The Next.js web page (web/) runs on a different origin in dev
# (localhost:3000) than the API (localhost:8000), so the browser needs an
# explicit CORS allowance to call it at all. Comma-separated, overridable
# for a real deployment's actual frontend origin.
CORS_ORIGINS = os.environ.get("STUDYRAG_CORS_ORIGINS", "http://localhost:3000").split(",")

EMBEDDING_MODEL = "text-embedding-3-small"
CHAT_MODEL = os.environ.get("STUDYRAG_CHAT_MODEL", "gpt-6-luna")
# gpt-6-luna doesn't accept a custom temperature (only the default, 1, is
# supported). Not applied anywhere right now; kept as a reminder for if
# the chat model changes to one that does support it.
CHAT_TEMPERATURE = 0.1

RETRIEVAL_K = 5

# "vector" (cosine similarity only) or "hybrid" (BM25 + vector, fused by
# Reciprocal Rank Fusion). Default is "vector" -- measured on the
# 30-question eval set, equal-weight hybrid regressed hit rate
# (29/30 -> 26/30): BM25's literal term-matching confused two real
# modules named "Software Architecture" and "Software Architectures"
# that a pure vector ranking told apart correctly. Kept available, not
# deleted, in case it's worth revisiting with unequal weighting -- see
# studyrag-decisions-log.md. Override with STUDYRAG_RETRIEVAL_MODE=hybrid.
RETRIEVAL_MODE = os.environ.get("STUDYRAG_RETRIEVAL_MODE", "vector")

# Fetch this many candidates cheaply by cosine similarity, then rerank
# down to RETRIEVAL_K. ENABLE_RERANKING defaults on -- measured directly
# against the known-fragile case (three documents' near-identical
# early-master-module clauses): pure cosine top-5 missed both the ÜPO and
# Bachelor PO passages needed to answer correctly, reranking recovered
# both. See studyrag-decisions-log.md for the full eval.
RERANK_CANDIDATE_K = 25
ENABLE_RERANKING = os.environ.get("STUDYRAG_ENABLE_RERANKING", "true").lower() == "true"

# Long-term memory for the core pipeline, not just the chair-lookup
# agent: known facts get injected into every generation call, and a
# cheap classifier decides after each question whether to write a new
# or updated durable fact. Off switch for eval runs, same reasoning as
# ENABLE_CHAIR_LOOKUP — regulation-lookup questions essentially never
# reveal a personal fact, so this would mostly be wasted classifier
# calls during a 30-question eval run.
ENABLE_MEMORY = os.environ.get("STUDYRAG_ENABLE_MEMORY", "true").lower() == "true"

# When the core pipeline abstains, try the chair-lookup agent
# (src/studyrag/chair_lookup/) before giving up -- but only for questions
# a classifier judges plausibly chair-answerable, and only when this flag
# is on. Several eval questions are deliberately unanswerable even by a
# chair page (tuition, library hours, etc.); this lets eval runs turn the
# agent off without a code change, since it's slower and hits real
# external sites. Default on for real usage.
ENABLE_CHAIR_LOOKUP = os.environ.get("STUDYRAG_ENABLE_CHAIR_LOOKUP", "true").lower() == "true"

# Below this top-1 retrieval score, skip the LLM call entirely and return
# a deterministic "not found" + contact -- a cheap pre-filter for clearly
# off-topic cases, not the only safety net. Answerable and unanswerable
# top-1 scores genuinely overlap in this corpus (an unanswerable question
# scored 0.616, higher than several answerable ones at 0.49-0.54), so no
# single cutoff cleanly separates them. Set low enough to never gate a
# real answerable question (lowest confirmed answerable score: 0.491);
# the LLM's own grounding in the system prompt reliably catches the rest.
ABSTENTION_THRESHOLD = 0.45

ABSTENTION_MESSAGE = (
    "I could not find this in the documents I have access to. "
    "Please contact the examination office (Zentrales Prüfungsamt) or the responsible chair."
)

# A greeting like "hi" retrieves nothing relevant and falls into the same
# ABSTENTION_THRESHOLD branch as a genuine unanswerable question -- without
# this, it got the same cold ABSTENTION_MESSAGE instead of a reply. Only
# fires inside that already-triggered branch
# (query_intent.classify_query_intent), so it adds zero cost to the
# normal, confidently-retrieved case. Off-topic replies are a fixed
# message, not model-generated, so the guardrail wording stays
# consistent and auditable.
ENABLE_CHITCHAT = os.environ.get("STUDYRAG_ENABLE_CHITCHAT", "true").lower() == "true"

OFF_TOPIC_MESSAGE = (
    "I'm specialized in the Master Informatik study regulations at RWTH Aachen — module content, CP, "
    "prerequisites, deadlines, and exam rules. I can't help with that, but feel free to ask me about your degree."
)
