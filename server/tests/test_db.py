"""Tests for database schema creation and migrations."""

import pytest

pytestmark = pytest.mark.smoke

EXPECTED_TABLES = [
    "ingest_log", "sessions", "messages", "self_reports", "model_pricing",
    "config", "survey_responses", "uplift_outputs", "api_keys", "scaffolds",
    "jobs", "script_results", "prompts",
]

SESSIONS_COLUMNS = [
    "session_id", "tool_source", "project_path", "project_name", "git_branch",
    "started_at", "ended_at", "total_input_tokens", "total_output_tokens",
    "total_cache_read_tokens", "total_cache_create_tokens", "total_cost_usd",
    "message_count", "tool_call_count", "model_primary", "scaffold",
]


def test_all_tables_exist(db):
    tables = [
        row["name"]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    ]
    for expected in EXPECTED_TABLES:
        assert expected in tables, f"Missing table: {expected}"


def test_sessions_columns(db):
    columns = [row[1] for row in db.execute("PRAGMA table_info(sessions)").fetchall()]
    for col in SESSIONS_COLUMNS:
        assert col in columns, f"Missing column: {col}"


def test_wal_mode(db):
    mode = db.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"


def test_foreign_keys_enabled(db):
    fk = db.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk == 1


def test_model_pricing_seeded(db):
    rows = db.execute("SELECT COUNT(*) as cnt FROM model_pricing").fetchone()
    assert rows["cnt"] >= 3  # At least the default models


def test_default_prompts_seeded(db):
    rows = db.execute("SELECT COUNT(*) as cnt FROM prompts WHERE is_default = 1").fetchone()
    assert rows["cnt"] >= 2  # compaction-default + judge-default


def test_default_surveys_seeded(db):
    row = db.execute("SELECT value FROM config WHERE key = 'surveys'").fetchone()
    assert row is not None
    import json
    surveys = json.loads(row["value"])
    assert "default" in surveys


def test_migrations_idempotent(db):
    """Running _migrate_db again should not fail."""
    from open_uplift.db import _migrate_db
    _migrate_db(db)  # Should not raise
    db.commit()
    # Tables should still exist
    tables = [
        row["name"]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    ]
    for expected in EXPECTED_TABLES:
        assert expected in tables
