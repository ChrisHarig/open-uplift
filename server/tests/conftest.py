"""Shared pytest fixtures for Open Uplift server tests."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from open_uplift.db import SCHEMA_SQL, _seed_default_prompts, DEFAULT_PROMPTS
from open_uplift.config import DEFAULT_PRICING
from open_uplift.llm_client import LLMResponse


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def db(tmp_path, monkeypatch):
    """In-memory SQLite with full schema, migrations, and pricing data."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row

    # Create schema
    conn.executescript(SCHEMA_SQL)

    # Seed pricing
    for model_name, prices in DEFAULT_PRICING.items():
        conn.execute(
            """INSERT OR IGNORE INTO model_pricing
               (model_name, input_cost_per_mtok, output_cost_per_mtok,
                cache_read_per_mtok, cache_create_per_mtok)
               VALUES (?, ?, ?, ?, ?)""",
            (model_name, prices["input"], prices["output"],
             prices["cache_read"], prices["cache_create"]),
        )

    # Seed config (surveys, questions) + default prompts
    from open_uplift.surveys import seed_default_config
    seed_default_config(conn)
    _seed_default_prompts(conn)

    conn.commit()

    # Monkeypatch get_db to return this connection
    from contextlib import contextmanager

    @contextmanager
    def _get_test_db():
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    monkeypatch.setattr("open_uplift.db.get_db", _get_test_db)
    # Also patch common import paths
    for mod in [
        "open_uplift.ingest.get_db",
        "open_uplift.job_queue.get_db",
        "open_uplift.scripts.get_api_key",
    ]:
        try:
            monkeypatch.setattr(mod, lambda *a, **kw: None)
        except AttributeError:
            pass

    # Re-patch ingest and job_queue to use our db
    monkeypatch.setattr("open_uplift.ingest.get_db", _get_test_db)
    monkeypatch.setattr("open_uplift.job_queue.get_db", _get_test_db)

    yield conn
    conn.close()


@pytest.fixture
def app(db, monkeypatch):
    """Flask test client with worker/scheduler disabled."""
    monkeypatch.setattr("open_uplift.api.start_worker", lambda: None)
    monkeypatch.setattr("open_uplift.api.start_scheduler", lambda: None)
    monkeypatch.setattr("open_uplift.job_queue.start_sync_scheduler", lambda: None)

    from contextlib import contextmanager

    @contextmanager
    def _get_test_db():
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise

    monkeypatch.setattr("open_uplift.api.get_db", _get_test_db)

    from open_uplift.api import create_app
    flask_app = create_app()
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


@pytest.fixture
def hub_app(db, monkeypatch):
    """Flask test client with hub=True and worker/scheduler disabled."""
    monkeypatch.setattr("open_uplift.api.start_worker", lambda: None)
    monkeypatch.setattr("open_uplift.api.start_scheduler", lambda: None)
    monkeypatch.setattr("open_uplift.job_queue.start_sync_scheduler", lambda: None)

    from contextlib import contextmanager

    @contextmanager
    def _get_test_db():
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise

    monkeypatch.setattr("open_uplift.api.get_db", _get_test_db)

    from open_uplift.api import create_app
    flask_app = create_app()
    flask_app.config["TESTING"] = True
    return flask_app.test_client()


def setup_hub_org(db, org_name="Test Org", admin_name="admin"):
    """Helper to create an org with admin member and invite code. Returns (org_id, admin_api_key, invite_code)."""
    import secrets
    from datetime import datetime, timezone

    from open_uplift.surveys import slugify

    org_id = slugify(org_name)
    now = datetime.now(timezone.utc).isoformat()
    sharing_config = json.dumps({
        "level": 1,
        "stats": {"tokens": True, "cost": True, "messages": True, "tool_calls": True, "uplift": True, "compacted_transcripts": False, "full_transcripts": False},
    })

    db.execute(
        "INSERT OR IGNORE INTO organizations (org_id, name, description, is_verified, created_at, sharing_config) VALUES (?, ?, '', 0, ?, ?)",
        (org_id, org_name, now, sharing_config),
    )

    admin_api_key = secrets.token_urlsafe(32)
    db.execute(
        "INSERT INTO hub_members (org_id, member_name, api_key, role, joined_at) VALUES (?, ?, ?, 'admin', ?)",
        (org_id, admin_name, admin_api_key, now),
    )

    invite_code = secrets.token_urlsafe(16)
    db.execute(
        "INSERT INTO hub_invites (invite_code, org_id, created_by, created_at) VALUES (?, ?, ?, ?)",
        (invite_code, org_id, admin_name, now),
    )

    db.commit()
    return org_id, admin_api_key, invite_code


@pytest.fixture
def sample_session(db):
    """Insert a realistic session with messages and return the session_id."""
    session_id = "test-session-00000000-0000-0000-0000-000000000001"
    now = datetime.now(timezone.utc).isoformat()

    db.execute(
        """INSERT INTO sessions
           (session_id, tool_source, project_path, project_name, git_branch,
            started_at, ended_at, total_input_tokens, total_output_tokens,
            total_cache_read_tokens, total_cache_create_tokens,
            total_cost_usd, message_count, tool_call_count, model_primary, scaffold)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            session_id, "claude_code", "/Users/dev/myproject", "myproject", "main",
            "2026-02-20T10:00:00Z", "2026-02-20T10:01:15Z",
            12500, 780, 5000, 100,
            0.05, 5, 3, "claude-sonnet-4-6", "claude_code",
        ),
    )

    messages = [
        (session_id, "2026-02-20T10:00:00Z", "user", None, 0, 0, 0, 0, 0.0, None),
        (session_id, "2026-02-20T10:00:05Z", "assistant", "claude-sonnet-4-6", 1500, 200, 500, 100, 0.01, "Read"),
        (session_id, "2026-02-20T10:00:15Z", "assistant", "claude-sonnet-4-6", 2000, 150, 800, 0, 0.008, "Edit"),
        (session_id, "2026-02-20T10:01:05Z", "assistant", "claude-sonnet-4-6", 3000, 250, 1200, 0, 0.012, "Write"),
        (session_id, "2026-02-20T10:01:15Z", "assistant", "claude-sonnet-4-6", 3500, 80, 1500, 0, 0.006, None),
    ]
    for msg in messages:
        db.execute(
            """INSERT INTO messages
               (session_id, timestamp, role, model, input_tokens, output_tokens,
                cache_read_tokens, cache_create_tokens, cost_usd, tool_names)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            msg,
        )
    db.commit()
    return session_id


@pytest.fixture
def sample_organization(db, sample_session):
    """Create an organization with 2 folders, one containing the sample session."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT OR IGNORE INTO organizations (org_id, name, description, is_verified, created_at) VALUES (?, ?, ?, ?, ?)",
        ("test-org", "Test Organization", "An org for testing", 1, now),
    )
    # Folder matching sample_session's project_path
    db.execute(
        "INSERT OR IGNORE INTO org_folders (org_id, folder_path, added_at) VALUES (?, ?, ?)",
        ("test-org", "/Users/dev/myproject", now),
    )
    # Second unrelated folder
    db.execute(
        "INSERT OR IGNORE INTO org_folders (org_id, folder_path, added_at) VALUES (?, ?, ?)",
        ("test-org", "/Users/dev/other-project", now),
    )
    db.commit()
    return "test-org"


@pytest.fixture
def sample_uplift_data(db, sample_session_with_results):
    """Add extra uplift_outputs for distribution/timeseries tests."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    session_id = sample_session_with_results

    resp = db.execute(
        "SELECT id FROM survey_responses WHERE session_id = ?", (session_id,)
    ).fetchone()
    resp_id = resp["id"]

    # llm-judge output for existing session
    db.execute(
        """INSERT OR IGNORE INTO uplift_outputs
           (session_id, survey_response_id, output_id, uplift_factor, metadata, timestamp)
           VALUES (?, ?, 'llm-judge', 2.8, '{}', ?)""",
        (session_id, resp_id, now),
    )
    db.execute(
        """INSERT OR IGNORE INTO judge_outputs
           (session_id, field_name, value_text, value_numeric, value_type, prompt_id, created_at)
           VALUES (?, 'success', 'true', 1.0, 'boolean', 'judge-default', ?)""",
        (session_id, now),
    )

    # Second session with its own outputs
    s2 = "test-session-00000000-0000-0000-0000-000000000002"
    db.execute(
        """INSERT OR IGNORE INTO sessions
           (session_id, tool_source, project_path, project_name, started_at, ended_at,
            total_input_tokens, total_output_tokens, total_cost_usd, message_count,
            tool_call_count, model_primary, scaffold)
           VALUES (?, 'claude_code', '/Users/dev/myproject', 'myproject',
                   '2026-02-21T10:00:00Z', '2026-02-21T10:30:00Z',
                   8000, 500, 0.03, 4, 2, 'claude-sonnet-4-6', 'claude_code')""",
        (s2,),
    )
    db.execute(
        """INSERT OR IGNORE INTO survey_responses
           (session_id, survey_id, tool_source, timestamp, answers, notes)
           VALUES (?, 'survey-1', 'claude_code', ?, '{"human-est": 5.0}', '')""",
        (s2, now),
    )
    resp2_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.execute(
        """INSERT OR IGNORE INTO uplift_outputs
           (session_id, survey_response_id, output_id, uplift_factor, metadata, timestamp)
           VALUES (?, ?, 'human-est', 5.0, '{}', ?)""",
        (s2, resp2_id, now),
    )
    db.execute(
        """INSERT OR IGNORE INTO uplift_outputs
           (session_id, survey_response_id, output_id, uplift_factor, metadata, timestamp)
           VALUES (?, ?, 'llm-judge', 4.2, '{}', ?)""",
        (s2, resp2_id, now),
    )
    db.execute(
        """INSERT OR IGNORE INTO judge_outputs
           (session_id, field_name, value_text, value_numeric, value_type, prompt_id, created_at)
           VALUES (?, 'success', 'true', 1.0, 'boolean', 'judge-default', ?)""",
        (s2, now),
    )
    db.commit()
    return [session_id, s2]


@pytest.fixture
def sample_prompt(db):
    """Insert a non-default custom prompt for CRUD tests."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        """INSERT OR IGNORE INTO prompts
           (prompt_id, category, name, description, system_prompt, created_at, is_default)
           VALUES ('custom-test', 'judge', 'Custom Test Prompt', 'A test prompt',
                   'You are a test prompt.', ?, 0)""",
        (now,),
    )
    db.commit()
    return "custom-test"


@pytest.fixture
def mock_llm(monkeypatch):
    """Monkeypatch LLMClient.complete and complete_with_tool to return canned responses.

    Default canned content matches the judge schema (tag_difficulty tool input). The
    compactor's per-turn calls re-use the same path; their JSON gets parsed but the
    fields it doesn't recognise are simply ignored downstream.
    """
    canned = LLMResponse(
        content='{"success": true, "tasks": [{"description": "Fix login bug", "succeeded": true, "estimated_minutes_without_ai": 30}], "total_minutes_without_ai": 30, "confidence": "medium", "reasoning": "Simple bug fix"}',
        input_tokens=1000,
        output_tokens=200,
        model="claude-sonnet-4-6",
        cost_usd=0.006,
    )
    compaction_canned = LLMResponse(
        content='{"actions": "Investigated the login bug and proposed a fix", "outcome": "Wrote code to fix login bug"}',
        input_tokens=200,
        output_tokens=50,
        model="claude-haiku-4-5-20251001",
        cost_usd=0.0005,
    )

    def fake_complete(self, system_prompt, user_prompt, **kwargs):
        return canned

    def fake_complete_with_tool(self, system_prompt, user_prompt, tool_name, **kwargs):
        if tool_name == "summarize_turn":
            return compaction_canned
        return canned

    monkeypatch.setattr("open_uplift.llm_client.LLMClient.complete", fake_complete)
    monkeypatch.setattr("open_uplift.llm_client.LLMClient.complete_with_tool", fake_complete_with_tool)
    return canned


@pytest.fixture
def cli_runner():
    """Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def sample_session_with_results(db, sample_session):
    """Session with survey response, compaction, and judge results."""
    session_id = sample_session
    now = datetime.now(timezone.utc).isoformat()

    # Survey response
    db.execute(
        """INSERT INTO survey_responses
           (session_id, survey_id, tool_source, timestamp, answers, notes)
           VALUES (?, 'survey-1', 'claude_code', ?, ?, 'test notes')""",
        (session_id, now, json.dumps({"human-est": 3.5})),
    )
    resp_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Uplift output
    db.execute(
        """INSERT INTO uplift_outputs
           (session_id, survey_response_id, output_id, uplift_factor, metadata, timestamp)
           VALUES (?, ?, 'human-est', 3.5, '{}', ?)""",
        (session_id, resp_id, now),
    )

    # Compaction result
    db.execute(
        """INSERT INTO script_results
           (session_id, script_id, status, result, error, input_tokens, output_tokens,
            cost_usd, started_at, completed_at, prompt_id)
           VALUES (?, 'transcript-compact', 'completed', ?, NULL, 1000, 200, 0.003, ?, ?, 'compaction-default')""",
        (session_id, json.dumps({"compacted_transcript": "## ACTIONS\nFixed a login bug.\n## OUTCOME\nSuccess."}), now, now),
    )

    # Judge result
    db.execute(
        """INSERT INTO script_results
           (session_id, script_id, status, result, error, input_tokens, output_tokens,
            cost_usd, started_at, completed_at, prompt_id)
           VALUES (?, 'llm-time-estimate', 'completed', ?, NULL, 1500, 300, 0.006, ?, ?, 'judge-default')""",
        (
            session_id,
            json.dumps({
                "success": True,
                "tasks": [{"description": "Fix login bug", "succeeded": True, "estimated_minutes_without_ai": 30}],
                "total_minutes_without_ai": 30,
                "confidence": "medium",
                "reasoning": "Simple bug fix",
                "minutes": 30,
                "model": "claude-sonnet-4-6",
                "cost_usd": 0.006,
            }),
            now, now,
        ),
    )

    db.commit()
    return session_id
