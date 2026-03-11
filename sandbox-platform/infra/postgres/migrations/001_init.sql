-- Migration 001 — Initial Schema
-- Platform Runtime: sessions + jobs tables
--
-- Run with:
--   psql -h localhost -U platform -d platform -f 001_init.sql

BEGIN;

-- ── Sessions ──────────────────────────────────────────────────────────────────
-- A session groups one or more tool executions under a single context.
CREATE TABLE IF NOT EXISTS sessions (
    id         TEXT        PRIMARY KEY,
    runtime    TEXT        NOT NULL DEFAULT 'wasm',  -- wasm | microvm | gui
    status     TEXT        NOT NULL DEFAULT 'active', -- active | stopped | expired
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Jobs ──────────────────────────────────────────────────────────────────────
-- A job is a single tool execution dispatched to a runtime tier.
CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT        PRIMARY KEY,
    session_id  TEXT        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    tool        TEXT        NOT NULL,
    tier        TEXT        NOT NULL DEFAULT 'wasm',  -- wasm | microvm | gui
    input       JSONB,
    status      TEXT        NOT NULL DEFAULT 'pending', -- pending | running | completed | failed
    output      TEXT,
    error_msg   TEXT,
    duration_ms BIGINT      NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Indexes ───────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_jobs_session ON jobs(session_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status  ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_tier    ON jobs(tier);

-- ── Tools registry ────────────────────────────────────────────────────────────
-- Registered tools and their runtime metadata. Populated by CI on tool push.
CREATE TABLE IF NOT EXISTS tools (
    name         TEXT        PRIMARY KEY,
    runtime      TEXT        NOT NULL,    -- wasm | microvm | gui
    version      TEXT        NOT NULL,
    artifact_ref TEXT        NOT NULL,    -- MinIO path: platform-tools/<runtime>/<name>/v1.wasm
    manifest     JSONB,
    healthy      BOOLEAN     NOT NULL DEFAULT true,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Seed: default tool routing rules ─────────────────────────────────────────
INSERT INTO tools (name, runtime, version, artifact_ref) VALUES
    ('html_parse',        'wasm',    'v1', 'platform-tools/wasm/html_parse/v1.wasm'),
    ('json_parse',        'wasm',    'v1', 'platform-tools/wasm/json_parse/v1.wasm'),
    ('markdown_convert',  'wasm',    'v1', 'platform-tools/wasm/markdown_convert/v1.wasm'),
    ('docx_generate',     'wasm',    'v1', 'platform-tools/wasm/docx_generate/v1.wasm'),
    ('python_run',        'microvm', 'v1', 'platform-tools/fc/python_run/v1'),
    ('bash_run',          'microvm', 'v1', 'platform-tools/fc/bash_run/v1'),
    ('git_clone',         'microvm', 'v1', 'platform-tools/fc/git_clone/v1'),
    ('file_ops',          'microvm', 'v1', 'platform-tools/fc/file_ops/v1'),
    ('browser_open',      'gui',     'v1', 'platform-tools/gui/browser_open/v1'),
    ('web_scrape',        'gui',     'v1', 'platform-tools/gui/web_scrape/v1'),
    ('excel_edit',        'gui',     'v1', 'platform-tools/gui/excel_edit/v1'),
    ('office_automation', 'gui',     'v1', 'platform-tools/gui/office_automation/v1')
ON CONFLICT (name) DO NOTHING;

COMMIT;
