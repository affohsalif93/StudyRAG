FROM python:3.12-slim

# poppler-utils (pdftotext): needed by the parsing/refresh scripts this
# image also runs (scripts/parse_handbook.py, parse_po.py,
# refresh_sources.py) — not by the API itself at runtime, but one image
# serves both rather than maintaining two. See studyrag-decisions-log.md
# for why pdftotext -raw was chosen over a pure-Python PDF library.
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

# Dependencies first, project code after: Docker's layer cache then
# keeps the (slow) dependency install across rebuilds that only touch
# source code, not pyproject.toml/uv.lock. --no-install-project defers
# installing this project itself until its source is actually present.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ src/
COPY scripts/ scripts/
RUN uv sync --frozen --no-dev

# Baked in, not left to a volume mount: a real cloud deploy (Render,
# Fly, etc.) has no host filesystem to mount data/ from the way
# `docker compose up`'s local dev setup does. studyrag.db (3.7MB) and
# the chunk index (5.5MB) are both small, fully derived from the
# pipeline's own scripts, and genuinely needed at API startup
# (studyrag.config.DB_PATH, api/app.py's INDEX_PATH) -- see
# .dockerignore for everything deliberately left out of this COPY
# (raw PDFs, intermediate extraction files, the unused LangChain Chroma
# store, runtime-written feedback/memory DBs). Locally, docker-compose's
# volume mount still overrides this with the host's own data/ at
# runtime, so this doesn't change local dev at all.
COPY data/ data/

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "studyrag.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
