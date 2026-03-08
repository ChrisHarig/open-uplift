"""Tests for the Codex transcript parser."""

import json
from pathlib import Path

import pytest

from open_uplift.transcript_codex import parse_codex_transcript

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestParseCodexTranscript:
    def test_basic_parsing_returns_transcript_and_stats(self):
        result = parse_codex_transcript(FIXTURES_DIR / "sample_codex_transcript.jsonl")
        assert "transcript" in result
        assert "stats" in result
        assert len(result["transcript"]) > 0

    def test_user_messages_extracted(self):
        result = parse_codex_transcript(FIXTURES_DIR / "sample_codex_transcript.jsonl")
        user_msgs = [t for t in result["transcript"] if t["role"] == "user"]
        assert len(user_msgs) >= 2
        assert user_msgs[0]["blocks"][0]["type"] == "text"
        assert "Fix" in user_msgs[0]["blocks"][0]["text"]

    def test_agent_message_text_blocks(self):
        result = parse_codex_transcript(FIXTURES_DIR / "sample_codex_transcript.jsonl")
        assistant_msgs = [t for t in result["transcript"] if t["role"] == "assistant"]
        text_blocks = [b for m in assistant_msgs for b in m["blocks"] if b["type"] == "text"]
        assert len(text_blocks) >= 1

    def test_command_execution_tool_use(self):
        result = parse_codex_transcript(FIXTURES_DIR / "sample_codex_transcript.jsonl")
        assistant_msgs = [t for t in result["transcript"] if t["role"] == "assistant"]
        tool_blocks = [b for m in assistant_msgs for b in m["blocks"] if b["type"] == "tool_use" and b["tool_name"] == "bash"]
        assert len(tool_blocks) >= 1
        assert "command" in tool_blocks[0]["input"]

    def test_file_change_tool_use(self):
        result = parse_codex_transcript(FIXTURES_DIR / "sample_codex_transcript.jsonl")
        assistant_msgs = [t for t in result["transcript"] if t["role"] == "assistant"]
        file_blocks = [b for m in assistant_msgs for b in m["blocks"] if b["type"] == "tool_use" and b["tool_name"] == "file_change"]
        assert len(file_blocks) >= 1
        assert "auth.py" in file_blocks[0]["result"]

    def test_thinking_blocks_from_reasoning(self):
        result = parse_codex_transcript(FIXTURES_DIR / "sample_codex_transcript.jsonl")
        assistant_msgs = [t for t in result["transcript"] if t["role"] == "assistant"]
        thinking = [b for m in assistant_msgs for b in m["blocks"] if b["type"] == "thinking"]
        assert len(thinking) >= 1

    def test_turn_boundaries_flush_blocks(self):
        result = parse_codex_transcript(FIXTURES_DIR / "sample_codex_transcript.jsonl")
        # Each turn.completed flushes pending blocks into an assistant message
        assistant_msgs = [t for t in result["transcript"] if t["role"] == "assistant"]
        assert len(assistant_msgs) >= 2

    def test_stats_count_user_messages(self):
        result = parse_codex_transcript(FIXTURES_DIR / "sample_codex_transcript.jsonl")
        assert result["stats"]["user_messages"] >= 2

    def test_stats_count_assistant_messages(self):
        result = parse_codex_transcript(FIXTURES_DIR / "sample_codex_transcript.jsonl")
        assert result["stats"]["assistant_messages"] >= 2

    def test_stats_count_tool_calls(self):
        result = parse_codex_transcript(FIXTURES_DIR / "sample_codex_transcript.jsonl")
        # bash commands + file changes
        assert result["stats"]["tool_calls"] >= 3

    def test_empty_file(self, tmp_path):
        empty = tmp_path / "empty.jsonl"
        empty.write_text("")
        result = parse_codex_transcript(empty)
        assert result["transcript"] == []
        assert result["stats"]["user_messages"] == 0

    def test_malformed_json_lines_skipped(self, tmp_path):
        f = tmp_path / "bad.jsonl"
        f.write_text('not json\n{"type":"item.completed","timestamp":"2026-01-15T10:00:00Z","item":{"type":"userMessage","content":[{"type":"text","text":"hello"}]}}\n{"type":"turn.completed","timestamp":"2026-01-15T10:00:05Z"}\n')
        result = parse_codex_transcript(f)
        # Should still parse the valid lines
        assert len(result["transcript"]) >= 1

    def test_content_as_string(self, tmp_path):
        f = tmp_path / "str_content.jsonl"
        lines = [
            json.dumps({"type": "item.completed", "timestamp": "2026-01-15T10:00:00Z", "item": {"type": "userMessage", "content": "hello world"}}),
            json.dumps({"type": "turn.completed", "timestamp": "2026-01-15T10:00:05Z"}),
        ]
        f.write_text("\n".join(lines))
        result = parse_codex_transcript(f)
        user_msgs = [t for t in result["transcript"] if t["role"] == "user"]
        assert len(user_msgs) == 1
        assert user_msgs[0]["blocks"][0]["text"] == "hello world"

    def test_orphaned_blocks_flushed_at_eof(self, tmp_path):
        """Blocks without a trailing turn.completed should still appear."""
        f = tmp_path / "no_turn.jsonl"
        lines = [
            json.dumps({"type": "item.completed", "timestamp": "2026-01-15T10:00:00Z", "item": {"type": "agentMessage", "text": "orphaned message"}}),
        ]
        f.write_text("\n".join(lines))
        result = parse_codex_transcript(f)
        assert len(result["transcript"]) == 1
        assert result["transcript"][0]["role"] == "assistant"

    def test_exit_code_marks_error(self, tmp_path):
        f = tmp_path / "error.jsonl"
        lines = [
            json.dumps({"type": "item.completed", "timestamp": "2026-01-15T10:00:00Z", "item": {"type": "commandExecution", "command": "false", "aggregatedOutput": "", "exitCode": 1}}),
            json.dumps({"type": "turn.completed", "timestamp": "2026-01-15T10:00:05Z"}),
        ]
        f.write_text("\n".join(lines))
        result = parse_codex_transcript(f)
        tool = result["transcript"][0]["blocks"][0]
        assert tool["is_error"] is True
