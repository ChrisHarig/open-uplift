"""Tests for the Codex provider."""

from pathlib import Path

from open_uplift.providers.codex import CodexProvider, ROLLOUT_FILE_RE, _extract_session_id

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_tool_name():
    provider = CodexProvider()
    assert provider.tool_name == "codex"


def test_scaffold_name():
    provider = CodexProvider()
    assert provider.scaffold_name == "codex"


def test_rollout_file_regex():
    assert ROLLOUT_FILE_RE.match(
        "rollout-2026-02-20T14-00-00-0199a213-81c0-7800-8aa1-bbab2a035a53.jsonl"
    )
    assert ROLLOUT_FILE_RE.match(
        "rollout-2025-08-29T14-50-52-620223ff-1234-12ab-1234-1234567890ab.jsonl"
    )
    assert not ROLLOUT_FILE_RE.match("not-a-rollout.jsonl")
    assert not ROLLOUT_FILE_RE.match("rollout-.jsonl")
    assert not ROLLOUT_FILE_RE.match("session.jsonl")


def test_extract_session_id():
    name = "rollout-2026-02-20T14-00-00-0199a213-81c0-7800-8aa1-bbab2a035a53.jsonl"
    assert _extract_session_id(name) == "0199a213-81c0-7800-8aa1-bbab2a035a53"


def test_extract_session_id_no_match():
    assert _extract_session_id("not-a-rollout.jsonl") is None


def test_discover_no_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "open_uplift.providers.codex.CODEX_SESSIONS_DIR",
        tmp_path / "nonexistent",
    )
    provider = CodexProvider()
    files = list(provider.discover_session_files())
    assert files == []


def test_discover_finds_sessions(tmp_path, monkeypatch):
    # Create date-sharded directory structure
    day_dir = tmp_path / "2026" / "02" / "20"
    day_dir.mkdir(parents=True)
    rollout = day_dir / "rollout-2026-02-20T14-00-00-0199a213-81c0-7800-8aa1-bbab2a035a53.jsonl"
    rollout.write_text("{}")

    # Also add a non-rollout file that should be ignored
    (day_dir / "other.jsonl").write_text("{}")

    monkeypatch.setattr(
        "open_uplift.providers.codex.CODEX_SESSIONS_DIR", tmp_path
    )
    provider = CodexProvider()
    files = list(provider.discover_session_files())
    assert len(files) == 1
    assert "rollout-" in files[0].name


def test_parse_session_basic():
    provider = CodexProvider()
    session, messages, offset = provider.parse_session(
        FIXTURES_DIR / "sample_codex_session.jsonl"
    )
    assert session.tool_source == "codex"
    assert session.session_id == "0199a213-81c0-7800-8aa1-bbab2a035a53"


def test_parse_session_extracts_project():
    provider = CodexProvider()
    session, messages, offset = provider.parse_session(
        FIXTURES_DIR / "sample_codex_session.jsonl"
    )
    assert session.project_path == "/Users/dev/myproject"
    assert session.project_name == "myproject"


def test_parse_session_extracts_model():
    provider = CodexProvider()
    session, messages, offset = provider.parse_session(
        FIXTURES_DIR / "sample_codex_session.jsonl"
    )
    assert session.model_primary == "o3"


def test_parse_session_timestamps():
    provider = CodexProvider()
    session, messages, offset = provider.parse_session(
        FIXTURES_DIR / "sample_codex_session.jsonl"
    )
    assert session.started_at
    assert session.ended_at
    assert session.started_at < session.ended_at


def test_parse_session_messages():
    provider = CodexProvider()
    session, messages, offset = provider.parse_session(
        FIXTURES_DIR / "sample_codex_session.jsonl"
    )
    user_msgs = [m for m in messages if m.role == "user"]
    assistant_msgs = [m for m in messages if m.role == "assistant"]
    assert len(user_msgs) == 2
    assert len(assistant_msgs) == 2


def test_parse_session_token_counts():
    provider = CodexProvider()
    session, messages, offset = provider.parse_session(
        FIXTURES_DIR / "sample_codex_session.jsonl"
    )
    assistant_msgs = [m for m in messages if m.role == "assistant"]
    # First turn: 2500 input, 350 output, 800 cached
    assert assistant_msgs[0].input_tokens == 2500
    assert assistant_msgs[0].output_tokens == 350
    assert assistant_msgs[0].cache_read_tokens == 800
    assert assistant_msgs[0].cache_create_tokens == 0
    # Second turn: 3200 input, 280 output, 1500 cached
    assert assistant_msgs[1].input_tokens == 3200
    assert assistant_msgs[1].output_tokens == 280
    assert assistant_msgs[1].cache_read_tokens == 1500


def test_parse_session_tool_calls():
    provider = CodexProvider()
    session, messages, offset = provider.parse_session(
        FIXTURES_DIR / "sample_codex_session.jsonl"
    )
    # 2 command executions + 2 file changes = 4 tool calls
    assert session.tool_call_count == 4


def test_parse_session_tool_names():
    provider = CodexProvider()
    session, messages, offset = provider.parse_session(
        FIXTURES_DIR / "sample_codex_session.jsonl"
    )
    assistant_msgs = [m for m in messages if m.role == "assistant"]
    # First turn has bash + file_change
    assert "bash" in assistant_msgs[0].tool_names
    assert "file_change" in assistant_msgs[0].tool_names
    # Second turn has file_change + bash
    assert "bash" in assistant_msgs[1].tool_names
    assert "file_change" in assistant_msgs[1].tool_names


def test_parse_session_offset_increases():
    provider = CodexProvider()
    _, _, offset = provider.parse_session(FIXTURES_DIR / "sample_codex_session.jsonl")
    assert offset > 0


def test_parse_session_incremental():
    provider = CodexProvider()
    _, msgs1, offset1 = provider.parse_session(
        FIXTURES_DIR / "sample_codex_session.jsonl"
    )
    assert len(msgs1) > 0

    # Re-parse from previous offset — no new content
    _, msgs2, offset2 = provider.parse_session(
        FIXTURES_DIR / "sample_codex_session.jsonl", from_offset=offset1
    )
    assert len(msgs2) == 0
    assert offset2 == offset1
