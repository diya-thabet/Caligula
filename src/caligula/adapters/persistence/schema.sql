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
