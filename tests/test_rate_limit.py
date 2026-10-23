"""The in-memory fallback path (no STUDYRAG_REDIS_URL set, same as CI
and local dev) -- enforce_rate_limit is pure, deterministic logic here,
unit-tested directly, same convention as test_engine.py's
_language_compatible. The Redis-backed path needs a real Redis
instance and isn't covered here.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers

from studyrag.api import rate_limit


class _FakeClient:
    def __init__(self, host: str) -> None:
        self.host = host


class _FakeRequest:
    def __init__(self, host: str, forwarded_for: str | None = None) -> None:
        self.client = _FakeClient(host)
        self.headers = Headers({"x-forwarded-for": forwarded_for} if forwarded_for else {})


@pytest.fixture(autouse=True)
def _reset_log():
    rate_limit._request_log.clear()
    yield
    rate_limit._request_log.clear()


def test_allows_requests_under_the_limit(monkeypatch):
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_MAX_REQUESTS", 3)
    request = _FakeRequest("1.2.3.4")
    for _ in range(3):
        rate_limit.enforce_rate_limit(request)  # must not raise


def test_blocks_once_the_limit_is_exceeded(monkeypatch):
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_MAX_REQUESTS", 3)
    request = _FakeRequest("1.2.3.4")
    for _ in range(3):
        rate_limit.enforce_rate_limit(request)
    with pytest.raises(HTTPException) as exc_info:
        rate_limit.enforce_rate_limit(request)
    assert exc_info.value.status_code == 429


def test_tracks_each_client_independently(monkeypatch):
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_MAX_REQUESTS", 1)
    rate_limit.enforce_rate_limit(_FakeRequest("1.2.3.4"))
    rate_limit.enforce_rate_limit(_FakeRequest("5.6.7.8"))  # a different client -- must not raise


def test_uses_the_first_forwarded_for_address_when_present(monkeypatch):
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_MAX_REQUESTS", 1)
    rate_limit.enforce_rate_limit(_FakeRequest("127.0.0.1", forwarded_for="9.9.9.9, 127.0.0.1"))
    with pytest.raises(HTTPException):
        # Same real client (9.9.9.9) behind the same proxy hop -- must still count against it.
        rate_limit.enforce_rate_limit(_FakeRequest("127.0.0.1", forwarded_for="9.9.9.9, 127.0.0.1"))
