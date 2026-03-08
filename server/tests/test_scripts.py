"""Tests for script execution engine."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from open_uplift.scripts import (
    get_script_results,
    run_script,
    run_transcript_compact,
    run_llm_time_estimate,
    _preprocess_transcript,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _setup_transcript(db, sample_session, monkeypatch, tmp_path):
    """Create a transcript file matching the session_id."""
    fixture = FIXTURES_DIR / "sample_session.jsonl"
    # Create a file whose name matches session_id
    transcript_file = tmp_path / f"{sample_session}.jsonl"
    transcript_file.write_text(fixture.read_text())
    db.execute(
        "INSERT INTO ingest_log (file_path, byte_offset, last_synced) VALUES (?, 0, '2026-01-01')",
        (str(transcript_file),),
    )
    monkeypatch.setattr("open_uplift.scripts.get_api_key", lambda db, provider: "fake-key")
    db.commit()


def test_run_script_dispatcher_compact(db, sample_session, mock_llm, monkeypatch, tmp_path):
    """run_script dispatches to transcript-compact."""
    _setup_transcript(db, sample_session, monkeypatch, tmp_path)

    result = run_script(db, "transcript-compact", sample_session)
    assert "error" not in result
    assert "compacted_transcript" in result


def test_run_script_dispatcher_judge(db, sample_session, mock_llm, monkeypatch, tmp_path):
    """run_script dispatches to llm-time-estimate."""
    _setup_transcript(db, sample_session, monkeypatch, tmp_path)

    result = run_script(db, "llm-time-estimate", sample_session)
    assert "error" not in result
    assert result.get("total_minutes_without_ai") == 30


def test_run_script_unknown(db, sample_session):
    with pytest.raises(ValueError, match="Unknown script"):
        run_script(db, "nonexistent-script", sample_session)


def test_transcript_compact_no_transcript(db, sample_session):
    result = run_transcript_compact(db, sample_session)
    assert result.get("error") == "Transcript file not found"


def test_transcript_compact_stores_result(db, sample_session, mock_llm, monkeypatch, tmp_path):
    _setup_transcript(db, sample_session, monkeypatch, tmp_path)

    run_transcript_compact(db, sample_session)

    results = get_script_results(db, sample_session)
    assert len(results) == 1
    assert results[0]["script_id"] == "transcript-compact"
    assert results[0]["status"] == "completed"


def test_llm_time_estimate_produces_output(db, sample_session, mock_llm, monkeypatch, tmp_path):
    _setup_transcript(db, sample_session, monkeypatch, tmp_path)

    result = run_llm_time_estimate(db, sample_session)
    assert result.get("minutes") == 30
    assert result.get("success") is True


def test_llm_time_estimate_uses_compacted(db, sample_session, mock_llm, monkeypatch):
    """Judge should prefer compacted transcript when available."""
    # Insert a compacted result
    db.execute(
        """INSERT INTO script_results
           (session_id, script_id, status, result, started_at, completed_at)
           VALUES (?, 'transcript-compact', 'completed', ?, '2026-01-01', '2026-01-01')""",
        (sample_session, json.dumps({"compacted_transcript": "Session summary here"})),
    )
    monkeypatch.setattr("open_uplift.scripts.get_api_key", lambda db, provider: "fake-key")
    db.commit()

    result = run_llm_time_estimate(db, sample_session)
    assert "error" not in result


def test_preprocess_transcript():
    transcript_data = {
        "transcript": [
            {
                "role": "user",
                "timestamp": "2026-01-01T10:00:00Z",
                "blocks": [{"type": "text", "text": "Hello world"}],
            },
            {
                "role": "assistant",
                "timestamp": "2026-01-01T10:00:05Z",
                "blocks": [
                    {"type": "text", "text": "Here is my response"},
                    {"type": "tool_use", "tool_name": "Read", "input": {"path": "foo.py"}},
                ],
            },
        ]
    }
    result = _preprocess_transcript(transcript_data)
    assert "USER: Hello world" in result
    assert "ASSISTANT: Here is my response" in result
    assert "Read" in result


def test_get_script_results_empty(db, sample_session):
    results = get_script_results(db, sample_session)
    assert results == []
