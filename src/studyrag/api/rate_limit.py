"""Per-IP rate limit for /ask, the one endpoint with open-ended OpenAI
cost per call. Backed by Redis when STUDYRAG_REDIS_URL is set, so the
limit is shared across restarts and multiple instances behind a load
balancer; falls back to an in-memory, single-process limiter otherwise
-- fine for local dev or a single instance, not for anything scaled out.
This is a cost backstop, not a security control.
"""

from __future__ import annotations

import os
import time
from collections import defaultdict

import redis
from fastapi import HTTPException, Request

RATE_LIMIT_MAX_REQUESTS = int(os.environ.get("STUDYRAG_RATE_LIMIT_MAX_REQUESTS", "20"))
RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("STUDYRAG_RATE_LIMIT_WINDOW_SECONDS", "600"))
REDIS_URL = os.environ.get("STUDYRAG_REDIS_URL")

_redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True) if REDIS_URL else None
_request_log: dict[str, list[float]] = defaultdict(list)


def client_key(request: Request) -> str:
    """The caller's real IP (first hop of X-Forwarded-For, if present).
    Also used to tag LangSmith traces, so abuse patterns can be
    correlated to a caller without plumbing it through every function
    signature between the API layer and the pipeline.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _count_redis(key: str, now: float) -> int:
    redis_key = f"studyrag:ratelimit:{key}"
    window_start = now - RATE_LIMIT_WINDOW_SECONDS
    pipe = _redis_client.pipeline()
    pipe.zremrangebyscore(redis_key, 0, window_start)
    pipe.zadd(redis_key, {str(now): now})
    pipe.zcard(redis_key)
    pipe.expire(redis_key, RATE_LIMIT_WINDOW_SECONDS)
    _, _, count, _ = pipe.execute()
    return count


def _count_memory(key: str, now: float) -> int:
    window_start = now - RATE_LIMIT_WINDOW_SECONDS
    recent = [t for t in _request_log[key] if t > window_start]
    recent.append(now)
    _request_log[key] = recent
    return len(recent)


def enforce_rate_limit(request: Request) -> None:
    key = client_key(request)
    now = time.time()
    if _redis_client is not None:
        try:
            count = _count_redis(key, now)
        except redis.RedisError:
            # Redis down shouldn't take the whole API down -- fail open
            # onto the in-memory path for this request instead of a 500.
            count = _count_memory(key, now)
    else:
        count = _count_memory(key, now)

    if count > RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: at most {RATE_LIMIT_MAX_REQUESTS} requests per {RATE_LIMIT_WINDOW_SECONDS} seconds.",
        )
