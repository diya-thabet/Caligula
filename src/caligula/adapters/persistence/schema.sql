-- Caligula evidence store (PostgreSQL 16 + pgvector).
-- Documents are append-only: a changed page is a new row sharing canonical_url.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id             text PRIMARY KEY,
    canonical_url  text NOT NULL,
    url            text NOT NULL,
    source_kind    text NOT NULL,
    publisher      text NOT NULL,
    title          text NOT NULL DEFAULT '',
    published_at   timestamptz,
    observed_at    timestamptz NOT NULL,
    raw_sha256     char(64) NOT NULL,
    text_sha256    char(64) NOT NULL,
    text           text NOT NULL,
    extraction     text NOT NULL DEFAULT 'plain',  -- plain | pdf_text | ocr
    cites          text[] NOT NULL DEFAULT '{}',
    derived_from   text[] NOT NULL DEFAULT '{}',
    -- 'simple' keeps Arabic and French tokens as-is (no language-specific stemming).
    tsv            tsvector GENERATED ALWAYS AS (to_tsvector('simple', title || ' ' || text)) STORED,
    embedding      vector(256),
    ingested_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS documents_canonical ON documents (canonical_url, observed_at);
CREATE INDEX IF NOT EXISTS documents_tsv ON documents USING gin (tsv);
CREATE INDEX IF NOT EXISTS documents_text_sha ON documents (text_sha256);

CREATE OR REPLACE FUNCTION documents_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'documents are append-only; store a new version instead';
END $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS documents_no_update ON documents;
CREATE TRIGGER documents_no_update BEFORE UPDATE OR DELETE ON documents
    FOR EACH ROW EXECUTE FUNCTION documents_append_only();

-- Restricted: contributor metadata (GPS, device). Grant to reviewers only.
CREATE TABLE IF NOT EXISTS custody_records (
    original_sha256 char(64) PRIMARY KEY,
    document_id     text REFERENCES documents (id),
    received_at     timestamptz NOT NULL,
    metadata        jsonb NOT NULL DEFAULT '{}',
    gps             jsonb
);

CREATE TABLE IF NOT EXISTS investigations (
    id          text PRIMARY KEY,
    mode        text NOT NULL,           -- factcheck | investigate
    allegation  jsonb NOT NULL,
    verdict     jsonb,
    trace       jsonb NOT NULL DEFAULT '[]',
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

-- The evidence ledger: one hash chain per case, append-only.
-- `at` is text, not timestamptz, on purpose. It is an input to the entry hash
-- (domain/services/ledger_chain.py), so re-reading a normalised timestamp would
-- recompute a different hash and the chain would read as tampered.
CREATE TABLE IF NOT EXISTS case_ledger (
    case_id  text NOT NULL,
    seq      int  NOT NULL,
    at       text NOT NULL,
    action   text NOT NULL,
    actor    text NOT NULL,
    data     jsonb NOT NULL,
    prev     text NOT NULL,
    hash     text NOT NULL,
    PRIMARY KEY (case_id, seq)
);

CREATE OR REPLACE FUNCTION case_ledger_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'the ledger is append-only; a past entry cannot be edited or removed';
END $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS case_ledger_no_update ON case_ledger;
CREATE TRIGGER case_ledger_no_update BEFORE UPDATE OR DELETE ON case_ledger
    FOR EACH ROW EXECUTE FUNCTION case_ledger_append_only();

-- A case as it stands: identity and lifecycle on their own columns, the reasoning
-- graph as jsonb. Snapshots are conveniences; the ledger and the documents are
-- the record of authority, and a verdict is always recomputed from those on restore.
CREATE TABLE IF NOT EXISTS cases (
    id             text PRIMARY KEY,
    claim          text NOT NULL,
    mode           text NOT NULL,
    poc            boolean NOT NULL DEFAULT true,
    created_by     text NOT NULL,
    created_at     timestamptz NOT NULL,
    updated_at     timestamptz NOT NULL DEFAULT now(),
    status         text NOT NULL,
    note           text NOT NULL DEFAULT '',
    origin         text NOT NULL DEFAULT 'api',   -- api | replay | cli
    round          int NOT NULL DEFAULT 1,
    added_by_code  jsonb NOT NULL DEFAULT '[]',
    intake         jsonb,
    decision       jsonb,
    allegation     jsonb,
    plan           jsonb,
    params         jsonb,
    review         text,
    summary        text,
    verdict        jsonb,
    attribution    jsonb,
    result         jsonb,
    workspace      jsonb NOT NULL DEFAULT '{}',
    status_history jsonb NOT NULL DEFAULT '[]',
    sign_off       jsonb
);
CREATE INDEX IF NOT EXISTS cases_created ON cases (created_at DESC);
