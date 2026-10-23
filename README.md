# StudyRAG

A citation-backed Q&A system and elective recommender for the Master Informatik study regulations at RWTH Aachen University.

Ask it a question about CP requirements, prerequisites, or thesis rules and it answers only from the actual module handbook and examination regulations, cites the exact passage, and says "I don't know, ask X" when the documents don't say — never a guessed answer. On top of that same data, a short quiz turns a career goal into a layered, cited list of electives to take, checked against the real prerequisite graph and CP rules.

> **Disclaimer:** A personal learning and portfolio project, not affiliated with RWTH Aachen University or an official advisory tool — always confirm anything important with the examination office or the responsible chair.

## Why

Study regulations are long, spread across several documents, and change every year — and in this setting, a wrong answer can cost a semester. StudyRAG enforces three guarantees in code, not just in the prompt:

1. Every answer is backed by a quoted, numbered source — checked automatically, not just trusted from the model.
2. It says "I couldn't find this" and names who to ask, rather than guessing.
3. It resists instructions hidden in retrieved content or in the question itself, tested with adversarial inputs in CI.

## Two parts, one data pipeline

**Q&A** — ask any question about the regulations and get a grounded, cited answer.

**Elective recommender** (`/quiz`) — answer a short quiz about your career goal, current progress, and constraints, and get a layered module recommendation (core / complementary / nice-to-have) backed by the real prerequisite graph, CP/area rule checks, and job-market evidence for which skills actually matter. Nine career tracks are covered: Software Engineer, Cybersecurity, Machine Learning Engineer, Scientific/Mathematical Software Engineer, Data Engineer, Distributed Systems Engineer, Theoretical Computer Scientist, Graphics & HCI Engineer, and Embedded Systems Engineer.

Both are built on the same retrieval core and the same parsed, structured regulation data.

## Architecture

```
raw PDFs (handbook, PO, ÜPO)
      │  pdftotext -raw
      ▼
extract + normalize
      ▼
SQLite (sources, modules, rules)
      │  chunked per module ("teaches" + "prerequisites") and per PO/ÜPO rule
      ▼
embed (OpenAI text-embedding-3-small) ──► vector store
      │
      ▼
question ─ rewrite if follow-up ─ retrieve ~25 ─ rerank to top-k
      │
      ▼
confident? ──no──► chair-answerable? ──no──► "not found" + contact
      │ yes                │ yes
      ▼                    ▼
answer + citations    chair-lookup agent (tool-calling: list chairs,
      │                fetch page, web search, remember/forget)
      ▼
citation check ─ version-conflict check
```

```
quiz answers ─► student profile ─► rule engine
                                       │
                 ┌─────────────────────┼─────────────────────┐
                 ▼                     ▼                     ▼
      Neo4j prerequisite graph   CP/area rules (PO)   track YAML (core/
      (foundation-first warn)    + research-vs-        complementary/
                                 industry weighting     nice-to-have + evidence)
                 └─────────────────────┼─────────────────────┘
                                       ▼
                     layered, cited recommendation + weak-skill
                     notes + CP budget + practical-skills gaps (O*NET)
```

Two independent answering pipelines exist for comparison: a **bare pipeline** (raw OpenAI SDK calls, a plain NumPy vector store) and a **LangChain pipeline** (LCEL chains, Chroma), which reproduces the bare pipeline's results to confirm neither is doing something the other isn't.

## Features

**Retrieval & trust**
- Hybrid dense + BM25 retrieval with LLM reranking
- Deterministic abstention below a similarity threshold, instead of letting the model improvise
- Automated citation checking and cross-document version-conflict detection
- Prompt-injection resistance tested in CI, plus a red-team suite (promptfoo) against the live API
- Per-IP rate limiting on `/ask` (Redis-backed, in-memory fallback), the one endpoint with open-ended OpenAI cost per call
- Optional LangSmith tracing for production visibility into real usage and abuse patterns
- A tool-calling agent that falls back to a chair's own website or a web search for questions a static corpus can't answer

**Elective recommender**
- A Neo4j-backed prerequisite graph extracted from the handbook's own text, with foundation-first warnings when a recommended module has an unmet real prerequisite
- CP/area requirement checks and early-master-cap checks against the actual examination regulations
- Research-vs-industry weighting that reorders a track's core layer based on the student's own stated goal
- Job-posting-evidence-backed skill weights (not guessed) and O*NET-sourced "practical skills no module teaches" gaps
- Three browsable graph views (`/graph`): module dependencies, a radial relevance map, and the department's chair structure

## Results

30-question eval set (`eval/questions.json`):

| Pipeline | Hit rate @5 | Correctness (keyword proxy) |
|---|---|---|
| Bare (NumPy + OpenAI SDK) | 30/30 (100%) | 29/30 (97%) |
| LangChain (Chroma + LCEL) | 30/30 (100%) | 29/30 (97%) |

| Trust feature | Result |
|---|---|
| Citation accuracy — rule-based | 97/103 (94%) |
| Citation accuracy — LLM judge | 73/103 (71%) |
| Prompt-injection resistance | 9/9 resisted |
| AI correctness judge vs. keyword proxy agreement | 29/30 (97%) |

Recommender persona suite (`eval/run_personas.py`), 27 hand-worked-out student profiles against the real database and prerequisite graph: 100% core precision/recall, zero constraint violations, zero spurious foundation-first warnings.

## How to run

```bash
uv sync
echo "OPENAI_API_KEY=your-key-here" > .env   # required

uvicorn studyrag.api.app:app --reload        # API on :8000
cd web && cp .env.local.example .env.local && npm install && npm run dev   # web app on :3000

# the recommender's quiz/graph views also need Neo4j, seeded once:
docker run -d --name studyrag-neo4j -p 7474:7474 -p 7687:7687 \
    -e NEO4J_AUTH=neo4j/studyrag_dev_password neo4j:5-community
python scripts/build_prerequisite_graph.py

pytest
```

Rebuilding the data pipeline from raw PDFs is in `scripts/`, every evaluation command is in `eval/`.

## Known limitations

- ~7% of handbook modules have an irregular PDF layout and go through LLM-assisted parsing, flagged `parse_status = needs_review` rather than silently trusted.
- Structured module fields (CP, language, offering cycle) aren't embedded in chunk text, so questions asking for them directly get a grounded "not stated in the passages" rather than a hallucinated number — correct, but not yet answerable.
- Hybrid (BM25 + vector) search was measured, not just assumed, and equal-weight fusion regressed the eval set on near-duplicate module titles — kept as a config option, default is vector-only.
- The rate limiter is a flat per-IP cost backstop, not real access control — no per-user quotas or abuse alerting.
- The chair-lookup agent's registry was compiled once and will drift as chairs change; it can self-heal a dead URL for one answer via web search but doesn't persist the fix back.

## Technology

- **Python**, dependency-managed with **uv**
- **OpenAI** for embeddings (`text-embedding-3-small`) and chat completion
- **Poppler's `pdftotext`** (`-raw` mode) for PDF extraction
- **LangChain** (`langchain-openai`, `langchain-chroma`) for the parallel comparison pipeline, and **LangChain's `create_agent()`** for the chair-lookup agent
- **Tavily** for that agent's web-search fallback
- **LangGraph's long-term memory** (`BaseStore`), backed by a small custom SQLite implementation
- **NumPy** for the bare pipeline's vector store, **Chroma** for the LangChain pipeline's, **SQLite FTS5** for BM25 keyword search
- **Neo4j** for the elective recommender's prerequisite graph
- **O*NET** (U.S. Dept. of Labor, CC BY 4.0) for the recommender's practical-skills evidence — see `data/onet/ATTRIBUTION.md`
- **FastAPI** + **uvicorn** for the HTTP API, **Redis** for the `/ask` rate limiter
- **promptfoo** for red-team testing against the live API, **LangSmith** for optional tracing
- **Next.js 16** (App Router, TypeScript, Tailwind v4) + **shadcn/ui** for the web app; **React Flow** + **dagre** for the dependency graph; **d3-force** for the radial relevance map and chairs graph
- **pytest** for tests; **GitHub Actions** for CI, a scheduled freshness check, and a scheduled red-team run
