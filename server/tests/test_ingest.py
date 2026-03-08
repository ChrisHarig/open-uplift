"""Tests for data ingestion pipeline."""

import json
from pathlib import Path

from open_uplift.ingest import calculate_cost
from open_uplift.providers.claude_code import ClaudeCodeProvider

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_calculate_cost_known_model(db):
    # Use a model that exists in DEFAULT_PRICING with exact prefix match
    cost = calculate_cost(db, "claude-sonnet-4-5-20250929", 1_000_000, 1_000_000, 0, 0)
    # sonnet 4.5: input=3.0, output=15.0 per Mtok
    assert cost == pytest.approx(18.0, abs=0.01)


def test_calculate_cost_unknown_model(db):
    cost = calculate_cost(db, "unknown-model-xyz", 1000, 1000, 0, 0)
    assert cost == 0.0


def test_calculate_cost_none_model(db):
    cost = calculate_cost(db, None, 1000, 1000, 0, 0)
    assert cost == 0.0


def test_calculate_cost_with_cache(db):
    cost = calculate_cost(db, "claude-haiku-4-5-20251001", 100_000, 50_000, 200_000, 10_000)
    assert cost > 0


def test_parse_jsonl_fixture():
    """Parse the sample JSONL fixture file."""
    provider = ClaudeCodeProvider()
    fixture = FIXTURES_DIR / "sample_session.jsonl"
    session, messages, offset = provider.parse_session(fixture)

    assert session.project_name == "myproject"
    assert session.project_path == "/Users/dev/myproject"
    assert session.git_branch == "main"
    assert session.tool_source == "claude_code"
    assert session.model_primary == "claude-sonnet-4-6"
    assert len(messages) > 0


def test_parse_fixture_message_counts():
    provider = ClaudeCodeProvider()
    fixture = FIXTURES_DIR / "sample_session.jsonl"
    session, messages, offset = provider.parse_session(fixture)

    user_msgs = [m for m in messages if m.role == "user"]
    assistant_msgs = [m for m in messages if m.role == "assistant"]
    assert len(user_msgs) >= 2
    assert len(assistant_msgs) >= 3


def test_parse_fixture_tool_calls():
    provider = ClaudeCodeProvider()
    fixture = FIXTURES_DIR / "sample_session.jsonl"
    session, messages, offset = provider.parse_session(fixture)

    assert session.tool_call_count >= 3
    # Check that tool names are captured
    tool_msgs = [m for m in messages if m.tool_names]
    assert len(tool_msgs) >= 1


def test_parse_fixture_tokens():
    provider = ClaudeCodeProvider()
    fixture = FIXTURES_DIR / "sample_session.jsonl"
    session, messages, offset = provider.parse_session(fixture)

    total_input = sum(m.input_tokens for m in messages)
    total_output = sum(m.output_tokens for m in messages)
    assert total_input > 0
    assert total_output > 0


def test_parse_from_offset():
    """Parsing from a non-zero offset should return a subset."""
    provider = ClaudeCodeProvider()
    fixture = FIXTURES_DIR / "sample_session.jsonl"

    # First parse: get full data and offset
    _, full_messages, full_offset = provider.parse_session(fixture)

    # Parse from midpoint
    mid = full_offset // 2
    _, partial_messages, new_offset = provider.parse_session(fixture, from_offset=mid)

    assert new_offset == full_offset
    assert len(partial_messages) <= len(full_messages)


def test_ingest_session_into_db(db, tmp_path, monkeypatch):
    """Full integration: sync_all discovers and ingests a session."""
    # Create a fake session file
    project_dir = tmp_path / "projects" / "-Users-dev-myproject"
    project_dir.mkdir(parents=True)

    session_file = project_dir / "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.jsonl"
    fixture = FIXTURES_DIR / "sample_session.jsonl"
    session_file.write_text(fixture.read_text())

    # Patch CLAUDE_PROJECTS_DIR
    monkeypatch.setattr("open_uplift.providers.claude_code.CLAUDE_PROJECTS_DIR", tmp_path / "projects")

    from open_uplift.ingest import sync_all
    stats = sync_all()

    assert stats["sessions_new"] == 1
    assert stats["messages_added"] > 0

    # Verify session in DB
    row = db.execute("SELECT * FROM sessions WHERE session_id = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'").fetchone()
    assert row is not None
    assert row["project_name"] == "myproject"


def test_ingest_duplicate_handling(db, tmp_path, monkeypatch):
    """Re-syncing the same file should not create duplicate sessions."""
    project_dir = tmp_path / "projects" / "-Users-dev-myproject"
    project_dir.mkdir(parents=True)

    session_file = project_dir / "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.jsonl"
    fixture = FIXTURES_DIR / "sample_session.jsonl"
    session_file.write_text(fixture.read_text())

    monkeypatch.setattr("open_uplift.providers.claude_code.CLAUDE_PROJECTS_DIR", tmp_path / "projects")

    from open_uplift.ingest import sync_all
    stats1 = sync_all()
    assert stats1["sessions_new"] == 1

    stats2 = sync_all()
    assert stats2["sessions_new"] == 0
    assert stats2["sessions_updated"] == 0

    # Only one session in DB
    count = db.execute("SELECT COUNT(*) as cnt FROM sessions").fetchone()["cnt"]
    assert count == 1


import pytest
