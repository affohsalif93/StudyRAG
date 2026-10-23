"""The HTTP API. Validation-failure cases don't reach `answer_question`
at all (Pydantic rejects them before the route body runs); the
real-answer cases call the live OpenAI API, same as the rest of this
project's eval/integration tests.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from studyrag.api.app import INDEX_PATH, app

# Module-level skip, not per-test: the TestClient fixture itself triggers
# FastAPI's lifespan, which loads INDEX_PATH at startup, so every test
# here would error at fixture setup rather than skip cleanly otherwise.
pytestmark = pytest.mark.skipif(not INDEX_PATH.exists(), reason="embedding index not built — run scripts/build_chunk_index.py first")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ask_rejects_empty_question(client):
    response = client.post("/ask", json={"question": ""})
    assert response.status_code == 422


def test_ask_rejects_missing_question(client):
    response = client.post("/ask", json={})
    assert response.status_code == 422


def test_ask_rejects_invalid_history_role(client):
    response = client.post("/ask", json={"question": "x", "history": [{"role": "system", "content": "hi"}]})
    assert response.status_code == 422


def test_ask_returns_a_real_grounded_answer(client):
    response = client.post("/ask", json={"question": "How many CP is the Masterarbeit module worth?"})
    assert response.status_code == 200
    body = response.json()
    assert "30" in body["answer"]
    assert body["abstained"] is False
    assert len(body["sources"]) > 0


def test_ask_uses_history_for_follow_up(client):
    response = client.post(
        "/ask",
        json={
            "question": "And what about the Bachelor thesis?",
            "history": [
                {"role": "user", "content": "How many CP is the Masterarbeit module worth?"},
                {"role": "assistant", "content": "The Masterarbeit module is worth 30 CP."},
            ],
        },
    )
    assert response.status_code == 200
    assert "15" in response.json()["answer"]


def test_feedback_accepts_up_or_down(client):
    response = client.post("/feedback", json={"question": "q", "answer": "a", "rating": "up"})
    assert response.status_code == 200
    assert "id" in response.json()


def test_feedback_rejects_invalid_rating(client):
    response = client.post("/feedback", json={"question": "q", "answer": "a", "rating": "sideways"})
    assert response.status_code == 422
