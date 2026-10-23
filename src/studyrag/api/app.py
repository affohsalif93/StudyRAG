"""HTTP API for StudyRAG. The embedding index is loaded once at startup
(FastAPI's lifespan), not per request.

Usage: uvicorn studyrag.api.app:app --reload
"""

from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from studyrag.answering.chat import answer_question
from studyrag.api.feedback_store import save_feedback
from studyrag.api.rate_limit import client_key, enforce_rate_limit
from studyrag.api.schemas import AskRequest, AskResponse, FeedbackRequest, FeedbackResponse
from studyrag.config import CORS_ORIGINS, DB_PATH, DEFAULT_USER_ID
from studyrag.recommender.chairs_graph import get_chairs_graph
from studyrag.recommender.engine import recommend
from studyrag.recommender.prerequisites import get_neo4j_driver, get_prerequisite_graph
from studyrag.recommender.profile import Profile
from studyrag.recommender.relevance import build_module_embeddings, score_relevance, similarity_edges
from studyrag.recommender.tracks import build_goal_graph, list_track_ids, load_track
from studyrag.retrieval.embed import load_index

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
INDEX_PATH = REPO_ROOT / "data" / "processed" / "embeddings" / "chunk_index.npz"
QUIZ_SCHEMA_PATH = REPO_ROOT / "data" / "quiz_stages.yaml"


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv(REPO_ROOT / ".env")
    app.state.vectors, app.state.metadata = load_index(str(INDEX_PATH))
    app.state.neo4j_driver = get_neo4j_driver()
    # Mean-pooled from the retrieval vectors already loaded above -- no
    # fresh embedding pass over the catalog. Per-track relevance scores
    # are cached lazily in graph_relevance() below.
    app.state.module_embeddings = build_module_embeddings(app.state.vectors, app.state.metadata)
    app.state.relevance_cache = {}
    app.state.similarity_edges = similarity_edges(app.state.module_embeddings)
    yield
    app.state.neo4j_driver.close()


app = FastAPI(
    title="StudyRAG",
    description="Citation-backed Q&A over the Master Informatik study regulations at RWTH Aachen.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse, dependencies=[Depends(enforce_rate_limit)])
def ask(request: AskRequest, http_request: Request) -> AskResponse:
    history = [turn.model_dump() for turn in request.history]
    result = answer_question(
        request.question,
        app.state.vectors,
        app.state.metadata,
        history=history,
        user_id=request.user_id or DEFAULT_USER_ID,
        source_filter=request.source_filter,
        langsmith_extra={"metadata": {"client_ip": client_key(http_request)}},
    )
    return AskResponse(
        question=result["question"],
        answer=result["answer"],
        sources=result["sources"],
        abstained=result["abstained"],
    )


@app.post("/feedback", response_model=FeedbackResponse)
def feedback(request: FeedbackRequest) -> FeedbackResponse:
    feedback_id = save_feedback(
        question=request.question,
        answer=request.answer,
        sources=request.sources,
        rating=request.rating,
        comment=request.comment,
    )
    return FeedbackResponse(id=feedback_id)


@app.get("/quiz/schema")
def quiz_schema() -> dict:
    """The quiz's single source of truth, served from data/quiz_stages.yaml
    with each job_title branch's track entries getting their real
    skills_weighted list injected from the track's own YAML file.
    """
    schema = yaml.safe_load(QUIZ_SCHEMA_PATH.read_text(encoding="utf-8"))
    for stage in schema["stages"]:
        if stage.get("type") != "job_title":
            continue
        for branch in stage.get("branches", {}).values():
            for title_entry in branch.get("titles", []):
                track = load_track(title_entry["track_id"])
                title_entry["skills"] = track.get("skills_weighted", [])
    return schema


@app.get("/modules/search")
def search_modules(q: str) -> list[dict]:
    """Type-ahead for the quiz's "already passed" stage — lets the student
    pick a real catalog module instead of typing an exact title match.
    """
    if len(q) < 2:
        return []
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute(
            "SELECT DISTINCT module_id, title FROM modules WHERE title LIKE ? ORDER BY title LIMIT 10", (f"%{q}%",)
        ).fetchall()
        return [{"module_id": r[0], "title": r[1]} for r in rows]
    finally:
        conn.close()


@app.get("/graph/relevance")
def graph_relevance(track_id: str) -> dict:
    """Every module in the catalog, scored by relevance to a track's goal
    (src/studyrag/recommender/relevance.py). Cached per track_id for the
    process lifetime -- the goal query embedding is the only new API call
    this makes.

    Also returns `real_edges` (the same handbook + goal edges
    GET /graph/prerequisites returns) and `similarity_edges`
    (content-embedding nearest-neighbors between modules, independent of
    any track) so the bubble view isn't just floating dots.
    """
    if track_id not in app.state.relevance_cache:
        app.state.relevance_cache[track_id] = score_relevance(track_id, app.state.module_embeddings)
    scores = app.state.relevance_cache[track_id]

    conn = sqlite3.connect(DB_PATH)
    try:
        placeholders = ",".join("?" * len(scores))
        rows = conn.execute(
            f"SELECT module_id, title, area, ects FROM modules WHERE module_id IN ({placeholders})", list(scores.keys())
        ).fetchall()
    finally:
        conn.close()

    # module_id isn't unique (cross-listed under two areas) -- keep the
    # first row seen per id.
    by_id: dict[str, tuple] = {}
    for row in rows:
        by_id.setdefault(row[0], row)

    real_edges = get_prerequisite_graph(app.state.neo4j_driver)["edges"] + build_goal_graph(track_id)["edges"]

    return {
        "track": {"track_id": track_id, "title": load_track(track_id)["title"]},
        "modules": [
            {"module_id": module_id, "title": row[1], "area": row[2], "ects": row[3], **scores[module_id]}
            for module_id, row in by_id.items()
        ],
        "real_edges": real_edges,
        "similarity_edges": app.state.similarity_edges,
    }


@app.get("/tracks")
def tracks() -> list[dict]:
    """Backs the standalone graph page's track picker."""
    return [{"track_id": tid, "title": load_track(tid)["title"]} for tid in list_track_ids()]


@app.get("/graph/chairs")
def graph_chairs() -> dict:
    """The chairs graph: chair nodes, the modules matched to them, and
    chair-to-chair subordination edges (src/studyrag/recommender/
    chairs_graph.py). A separate endpoint from /graph/relevance and
    /graph/prerequisites on purpose -- see studyrag-decisions-log.md.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        return get_chairs_graph(conn)
    finally:
        conn.close()


@app.get("/graph/prerequisites")
def graph_prerequisites(track_id: str | None = None) -> dict:
    """Nodes + edges for the prerequisite graph visualization -- the
    handbook-derived graph (src/studyrag/recommender/prerequisites.py)
    always, plus a track's goal-relevance graph
    (src/studyrag/recommender/tracks.py:build_goal_graph) when a track_id
    is given. Module nodes that appear in both are merged by module_id.
    """
    graph = get_prerequisite_graph(app.state.neo4j_driver)
    nodes_by_id = {n["module_id"]: n for n in graph["nodes"]}
    edges = list(graph["edges"])

    if track_id:
        goal_graph = build_goal_graph(track_id)
        for n in goal_graph["nodes"]:
            nodes_by_id.setdefault(n["module_id"], n)
        edges.extend(goal_graph["edges"])

    return {"nodes": list(nodes_by_id.values()), "edges": edges}


@app.post("/recommend")
def recommend_endpoint(profile: Profile) -> dict:
    """Turns a completed profile into a layered, cited elective
    recommendation. The profile itself is never stored server-side
    (client-side storage, see studyrag-decisions-log.md) -- this
    endpoint is stateless, given the whole profile each call.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        return recommend(profile, conn, app.state.neo4j_driver)
    finally:
        conn.close()
