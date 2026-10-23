-- StudyRAG database schema. The module/rule columns mirror
-- studyrag-handbook-module-schema.md's JSON schema 1:1.
--
-- modules/exam_nodes/rules are fully derived from data/processed/*.jsonl
-- and are wiped+reloaded on every build (src/studyrag/db/loader.py) —
-- never hand-edited. sources is the one small, hand-maintained table.
--
-- Primary keys are plain `INTEGER PRIMARY KEY`, deliberately NOT
-- AUTOINCREMENT: AUTOINCREMENT guarantees an id is never reused, even
-- after a full wipe+reload from the same JSONL, which breaks the "safe
-- to rebuild from scratch, same result" property chunk_index.npz and
-- chunks_fts both rely on staying in sync with these row ids. A plain
-- INTEGER PRIMARY KEY reuses the lowest free rowid after a full wipe, so
-- the same JSONL always produces the same ids again.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    doc_type TEXT NOT NULL,       -- 'module_handbook' | 'po' | 'uepo'
    version TEXT,
    valid_for TEXT,
    language TEXT,
    terms_note TEXT,
    local_path TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    retrieved_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS modules (
    id INTEGER PRIMARY KEY,
    -- module_id is NOT unique: one real module (1215842) is legitimately
    -- cross-listed under two areas with identical content.
    module_id TEXT NOT NULL,
    source_id TEXT NOT NULL REFERENCES sources(id),
    schema_version INTEGER,
    title TEXT,
    module_type TEXT,
    version TEXT,
    duration_semesters INTEGER,
    cycle TEXT,
    valid_from TEXT,
    valid_until TEXT,
    level TEXT,
    language TEXT,
    content TEXT,
    learning_objectives TEXT,
    teaching_methods TEXT,
    prerequisites TEXT,
    recommended_requirements TEXT,
    "references" TEXT,
    examination_terms TEXT,
    miscellaneous TEXT,
    coordinator TEXT,
    ects REAL,
    contact_time_wsh REAL,
    examination_duration_min_raw TEXT,
    total_hours REAL,
    contact_hours REAL,
    page_start INTEGER,
    page_end INTEGER,
    wahlpflicht_category TEXT,
    area TEXT,
    contributing_faculty TEXT,
    area_breadcrumb_json TEXT,     -- JSON array, see area_breadcrumb in the schema doc
    toc_page_expected INTEGER,
    translation_source TEXT,
    parse_status TEXT,
    parse_method TEXT,
    llm_notes TEXT,
    normalization_status TEXT,
    unmapped_raw_values_json TEXT, -- JSON array of {field, value}
    raw_text TEXT
);

CREATE INDEX IF NOT EXISTS idx_modules_module_id ON modules(module_id);
CREATE INDEX IF NOT EXISTS idx_modules_source_id ON modules(source_id);

-- Always empty for now: the exam-node sub-table inside each module block
-- isn't parsed yet. Table exists so the shape is ready once it is.
CREATE TABLE IF NOT EXISTS exam_nodes (
    id INTEGER PRIMARY KEY,
    module_id INTEGER NOT NULL REFERENCES modules(id),
    title TEXT,
    recommended_semester_winter INTEGER,
    recommended_semester_summer INTEGER,
    ects REAL,
    contact_time REAL
);

CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(id),
    paragraph TEXT NOT NULL,
    paragraph_title TEXT,
    absatz TEXT,                   -- NULL = text with no numbered Absatz
    text TEXT,
    numeric_values_cp_json TEXT,   -- JSON array of ints found in this Absatz
    cross_reference TEXT,          -- e.g. "§ 9 ÜPO", NULL if none
    is_template_example INTEGER NOT NULL DEFAULT 0,  -- 1 = ÜPO annex boilerplate, not operative text
    verification_status TEXT
);

CREATE INDEX IF NOT EXISTS idx_rules_source_paragraph ON rules(source_id, paragraph);

-- module -> chair, derived from matching each module's real `coordinator`
-- name against real scraped chair pages (scripts/link_chair_modules.py)
-- -- never hand-edited, re-run that script to regenerate. Only its
-- "matched" (unambiguous, exactly-one-chair) results are loaded here;
-- ambiguous/unmatched stay in the script's report file for human review.
CREATE TABLE IF NOT EXISTS module_chairs (
    module_id TEXT NOT NULL,
    chair_id TEXT NOT NULL,
    matched_people_json TEXT,  -- JSON array of the coordinator name(s) that matched
    PRIMARY KEY (module_id, chair_id)
);

-- BM25 keyword search over the exact same chunks the vector store embeds
-- (src/studyrag/retrieval/chunks.py), so keyword and vector results can
-- be fused by chunk_id in hybrid search. Populated by
-- src/studyrag/db/loader.py:load_fts_index, not here.
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(chunk_id UNINDEXED, text);
