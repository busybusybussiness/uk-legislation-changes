-- Phase 1 schema — EXACTLY the 6 tables mandated by MASTER-PROMPT-V2 §28.
-- Portable SQLite / Cloudflare D1 SQL. No ORM, no migrations framework.
--
-- Design rules enforced here, not in a prompt (§4, §31):
--   * history is APPEND-ONLY. record_versions has no UPDATE path.
--   * every write is attributable to an ingest_run.
--   * audit_events is immutable and outside agent authority (§25).

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- 1. sources — the registry. License + rate limits live as DATA and are
--    enforced by the ingestion service (§23: "the ingestion service enforces
--    these, not a prompt").
CREATE TABLE IF NOT EXISTS sources (
  id                  TEXT PRIMARY KEY,
  name                TEXT NOT NULL,
  operator            TEXT NOT NULL,
  base_url            TEXT NOT NULL,
  license_id          TEXT NOT NULL,
  license_url         TEXT NOT NULL,
  attribution_text    TEXT NOT NULL,          -- REQUIRED by OGL v3; rendered on every surface
  commercial_use      INTEGER NOT NULL,        -- 1 = permitted, verbatim-verified
  redistribution      INTEGER NOT NULL,
  requires_api_key    INTEGER NOT NULL DEFAULT 0,
  max_requests_per_sec REAL    NOT NULL,       -- enforced by the limiter
  crawl_delay_declared REAL,                   -- from robots.txt, if any
  restricted_fields   TEXT NOT NULL DEFAULT '[]',  -- JSON: dropped at the boundary
  terms_verified_on   TEXT NOT NULL,
  terms_excerpt       TEXT NOT NULL,           -- verbatim operative language
  notes               TEXT
);

-- 2. records — stable identity of a thing we track (one legislative provision).
CREATE TABLE IF NOT EXISTS records (
  id            TEXT PRIMARY KEY,              -- e.g. ukpga/1998/42/section/1
  source_id     TEXT NOT NULL REFERENCES sources(id),
  record_type   TEXT NOT NULL,
  jurisdiction  TEXT,
  title         TEXT,
  uri           TEXT NOT NULL,
  first_seen_at TEXT NOT NULL,
  last_seen_at  TEXT NOT NULL,
  UNIQUE(source_id, uri)
);
CREATE INDEX IF NOT EXISTS idx_records_source ON records(source_id);

-- 3. record_versions — APPEND-ONLY point-in-time snapshots. The asset.
--    content_hash makes re-ingestion idempotent (§16 idempotency principle).
CREATE TABLE IF NOT EXISTS record_versions (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  record_id      TEXT NOT NULL REFERENCES records(id),
  valid_from     TEXT NOT NULL,                -- RestrictStartDate: when the law CHANGED
  retrieved_at   TEXT NOT NULL,                -- when WE observed it (bitemporal)
  content_hash   TEXT NOT NULL,
  content        TEXT NOT NULL,
  content_bytes  INTEGER NOT NULL,
  ingest_run_id  INTEGER NOT NULL REFERENCES ingest_runs(id),
  UNIQUE(record_id, valid_from, content_hash)  -- idempotent re-ingest
);
CREATE INDEX IF NOT EXISTS idx_versions_record ON record_versions(record_id, valid_from);

-- 4. record_changes — computed diffs. Derived, rebuildable, never authoritative.
CREATE TABLE IF NOT EXISTS record_changes (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  record_id      TEXT NOT NULL REFERENCES records(id),
  from_version   INTEGER REFERENCES record_versions(id),
  to_version     INTEGER NOT NULL REFERENCES record_versions(id),
  change_date    TEXT NOT NULL,
  change_type    TEXT NOT NULL,                -- INITIAL | AMENDED | PROSPECTIVE
  chars_added    INTEGER NOT NULL DEFAULT 0,
  chars_removed  INTEGER NOT NULL DEFAULT 0,
  summary        TEXT,                         -- DETERMINISTIC text. No LLM. (§31)
  detected_at    TEXT NOT NULL,
  UNIQUE(record_id, to_version)
);
CREATE INDEX IF NOT EXISTS idx_changes_date ON record_changes(change_date DESC);

-- 5. ingest_runs — resumable checkpoints. A 15-20 min backfill WILL be interrupted.
CREATE TABLE IF NOT EXISTS ingest_runs (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id       TEXT NOT NULL REFERENCES sources(id),
  started_at      TEXT NOT NULL,
  finished_at     TEXT,
  status          TEXT NOT NULL,               -- RUNNING | COMPLETED | FAILED | INTERRUPTED
  cursor          TEXT,                        -- resume point
  requests_made   INTEGER NOT NULL DEFAULT 0,
  http_429_count  INTEGER NOT NULL DEFAULT 0,
  records_seen    INTEGER NOT NULL DEFAULT 0,
  versions_written INTEGER NOT NULL DEFAULT 0,
  changes_written INTEGER NOT NULL DEFAULT 0,
  truncation_alerts INTEGER NOT NULL DEFAULT 0, -- the silent-cap trap detector
  error           TEXT
);

-- 6. audit_events — immutable. Answers "why did we do that?" (§25)
CREATE TABLE IF NOT EXISTS audit_events (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  occurred_at  TEXT NOT NULL,
  actor        TEXT NOT NULL,                  -- 'ingest-service' — never an agent in Phase 1
  action       TEXT NOT NULL,
  subject      TEXT,
  ingest_run_id INTEGER REFERENCES ingest_runs(id),
  severity     TEXT NOT NULL DEFAULT 'INFO',   -- INFO | WARN | CRITICAL
  detail       TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_events(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_sev ON audit_events(severity, occurred_at DESC);

-- Guard: block UPDATEs to version history at the DATABASE level, so no
-- application bug (or future agent) can rewrite history. §25.
CREATE TRIGGER IF NOT EXISTS no_update_versions
BEFORE UPDATE ON record_versions
BEGIN
  SELECT RAISE(ABORT, 'record_versions is append-only');
END;

CREATE TRIGGER IF NOT EXISTS no_delete_versions
BEFORE DELETE ON record_versions
BEGIN
  SELECT RAISE(ABORT, 'record_versions is append-only');
END;

CREATE TRIGGER IF NOT EXISTS no_update_audit
BEFORE UPDATE ON audit_events
BEGIN
  SELECT RAISE(ABORT, 'audit_events is immutable');
END;

CREATE TRIGGER IF NOT EXISTS no_delete_audit
BEFORE DELETE ON audit_events
BEGIN
  SELECT RAISE(ABORT, 'audit_events is immutable');
END;
