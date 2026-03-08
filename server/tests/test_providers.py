"""Tests for the Claude Code provider."""

import re
from pathlib import Path

from open_uplift.providers.claude_code import ClaudeCodeProvider, SESSION_FILE_RE

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_tool_name():
    provider = ClaudeCodeProvider()
    assert provider.tool_name == "claude_code"


def test_scaffold_name():
    provider = ClaudeCodeProvider()
    assert provider.scaffold_name == "claude_code"


def test_session_file_regex():
    assert SESSION_FILE_RE.match("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.jsonl")
    assert SESSION_FILE_RE.match("12345678-1234-1234-1234-123456789abc.jsonl")
    assert not SESSION_FILE_RE.match("not-a-uuid.jsonl")
    assert not SESSION_FILE_RE.match("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.txt")
    assert not SESSION_FILE_RE.match("readme.md")


def test_discover_no_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "open_uplift.providers.claude_code.CLAUDE_PROJECTS_DIR",
        tmp_path / "nonexistent",
    )
    provider = ClaudeCodeProvider()
    files = list(provider.discover_session_files())
    assert files == []


def test_discover_finds_sessions(tmp_path, monkeypatch):
    project_dir = tmp_path / "-Users-dev-project"
    project_dir.mkdir()
    session = project_dir / "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.jsonl"
    session.write_text("{}")

    # Also add a non-session file that should be ignored
    (project_dir / "readme.md").write_text("hi")

    monkeypatch.setattr(
        "open_uplift.providers.claude_code.CLAUDE_PROJECTS_DIR", tmp_path
    )
    provider = ClaudeCodeProvider()
    files = list(provider.discover_session_files())
    assert len(files) == 1
    assert files[0].name == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.jsonl"


def test_parse_session_extracts_project():
    provider = ClaudeCodeProvider()
    session, messages, offset = provider.parse_session(FIXTURES_DIR / "sample_session.jsonl")
    assert session.project_path == "/Users/dev/myproject"
    assert session.project_name == "myproject"


def test_parse_session_extracts_git_branch():
    provider = ClaudeCodeProvider()
    session, messages, offset = provider.parse_session(FIXTURES_DIR / "sample_session.jsonl")
    assert session.git_branch == "main"


def test_parse_session_extracts_model():
    provider = ClaudeCodeProvider()
    session, messages, offset = provider.parse_session(FIXTURES_DIR / "sample_session.jsonl")
    assert session.model_primary == "claude-sonnet-4-6"


def test_parse_session_timestamps():
    provider = ClaudeCodeProvider()
    session, messages, offset = provider.parse_session(FIXTURES_DIR / "sample_session.jsonl")
    assert session.started_at
    assert session.ended_at
    assert session.started_at < session.ended_at


def test_parse_session_offset_increases():
    provider = ClaudeCodeProvider()
    _, _, offset = provider.parse_session(FIXTURES_DIR / "sample_session.jsonl")
    assert offset > 0
