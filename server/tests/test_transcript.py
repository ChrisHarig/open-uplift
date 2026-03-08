"""Tests for transcript parsing."""

from pathlib import Path

from open_uplift.transcript import parse_transcript

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_parse_transcript_basic():
    result = parse_transcript(FIXTURES_DIR / "sample_session.jsonl")
    assert "transcript" in result
    assert "stats" in result
    assert len(result["transcript"]) > 0


def test_parse_transcript_stats():
    result = parse_transcript(FIXTURES_DIR / "sample_session.jsonl")
    stats = result["stats"]
    assert stats["user_messages"] >= 1
    assert stats["assistant_messages"] >= 1
    assert stats["tool_calls"] >= 1


def test_parse_transcript_roles():
    result = parse_transcript(FIXTURES_DIR / "sample_session.jsonl")
    roles = {entry["role"] for entry in result["transcript"]}
    assert "user" in roles
    assert "assistant" in roles


def test_parse_transcript_blocks():
    result = parse_transcript(FIXTURES_DIR / "sample_session.jsonl")
    for entry in result["transcript"]:
        assert "blocks" in entry
        assert len(entry["blocks"]) >= 1
        for block in entry["blocks"]:
            assert "type" in block


def test_parse_transcript_tool_use():
    result = parse_transcript(FIXTURES_DIR / "sample_session.jsonl")
    tool_blocks = []
    for entry in result["transcript"]:
        for block in entry["blocks"]:
            if block["type"] == "tool_use":
                tool_blocks.append(block)

    assert len(tool_blocks) >= 1
    for tb in tool_blocks:
        assert "tool_name" in tb
        assert "input" in tb


def test_parse_transcript_tool_result_attached():
    """tool_result should be attached to the preceding tool_use."""
    result = parse_transcript(FIXTURES_DIR / "sample_session.jsonl")
    tool_blocks = []
    for entry in result["transcript"]:
        for block in entry["blocks"]:
            if block["type"] == "tool_use":
                tool_blocks.append(block)

    # At least one tool should have a result
    with_results = [t for t in tool_blocks if t.get("result") is not None]
    assert len(with_results) >= 1


def test_parse_transcript_thinking_blocks():
    result = parse_transcript(FIXTURES_DIR / "sample_session.jsonl")
    thinking_blocks = []
    for entry in result["transcript"]:
        for block in entry["blocks"]:
            if block["type"] == "thinking":
                thinking_blocks.append(block)

    assert len(thinking_blocks) >= 1
    assert thinking_blocks[0]["text"]


def test_parse_transcript_timestamps():
    result = parse_transcript(FIXTURES_DIR / "sample_session.jsonl")
    for entry in result["transcript"]:
        assert "timestamp" in entry


def test_parse_empty_file(tmp_path):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    result = parse_transcript(empty)
    assert result["transcript"] == []
    assert result["stats"]["user_messages"] == 0


def test_parse_malformed_json(tmp_path):
    """Malformed lines should be skipped."""
    bad = tmp_path / "bad.jsonl"
    bad.write_text("not json\n{invalid\n")
    result = parse_transcript(bad)
    assert result["transcript"] == []
