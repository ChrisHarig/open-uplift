"""Tests for CLI formatting utilities."""

from open_uplift.cli.formatting import (
    format_judge_results,
    format_session_detail,
    format_session_table,
    format_survey_results,
    format_telemetry,
    format_transcript,
    status_markers,
)


def test_status_markers_all_true():
    assert status_markers(True, True, True) == "[S][C][J]"


def test_status_markers_all_false():
    assert status_markers(False, False, False) == "[ ][ ][ ]"


def test_status_markers_mixed():
    assert status_markers(True, False, True) == "[S][ ][J]"


def test_format_session_table_basic():
    rows = [
        {
            "session_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "started_at": "2026-02-20T10:00:00Z",
            "project_name": "myproject",
            "model_primary": "claude-sonnet-4-6",
            "message_count": 5,
            "total_cost_usd": 0.05,
            "uplift_factor": 3.5,
            "has_survey": 1,
            "has_compaction": 0,
            "has_judge": 0,
        },
        {
            "session_id": "11111111-2222-3333-4444-555555555555",
            "started_at": "2026-02-19T09:00:00Z",
            "project_name": None,
            "model_primary": None,
            "message_count": 3,
            "total_cost_usd": 0.02,
            "uplift_factor": None,
            "has_survey": 0,
            "has_compaction": 1,
            "has_judge": 1,
        },
    ]
    table = format_session_table(rows)
    assert table.title == "Sessions"
    assert table.row_count == 2


def test_format_session_table_custom_title():
    table = format_session_table([], title="Test Title")
    assert table.title == "Test Title"
    assert table.row_count == 0


def test_format_session_detail():
    session = {
        "session_id": "abc-123",
        "project_name": "myproject",
        "project_path": "/Users/dev/myproject",
        "git_branch": "main",
        "started_at": "2026-02-20T10:00:00Z",
        "ended_at": "2026-02-20T10:01:15Z",
        "message_count": 5,
        "tool_call_count": 3,
        "model_primary": "claude-sonnet-4-6",
        "total_cost_usd": 0.05,
        "has_survey": 1,
        "has_compaction": 0,
        "has_judge": 0,
    }
    panel = format_session_detail(session)
    assert panel.title == "Session Detail"


def test_format_session_detail_with_time_data():
    session = {
        "session_id": "abc-123",
        "project_name": "myproject",
        "project_path": "/tmp",
        "git_branch": "main",
        "started_at": "2026-02-20T10:00:00Z",
        "ended_at": "2026-02-20T10:30:00Z",
        "message_count": 5,
        "tool_call_count": 3,
        "model_primary": "claude-sonnet-4-6",
        "total_cost_usd": 0.05,
        "has_survey": 0,
        "has_compaction": 0,
        "has_judge": 0,
    }
    time_data = {"active_minutes": 20, "active_windows": 2}
    panel = format_session_detail(session, time_data)
    assert panel.title == "Session Detail"


def test_format_telemetry_summary():
    session = {
        "total_input_tokens": 12500,
        "total_output_tokens": 780,
        "total_cache_read_tokens": 5000,
        "total_cache_create_tokens": 100,
        "total_cost_usd": 0.05,
    }
    panel = format_telemetry(session)
    assert panel.title == "Telemetry"


def test_format_telemetry_with_messages():
    session = {
        "total_input_tokens": 12500,
        "total_output_tokens": 780,
        "total_cache_read_tokens": 5000,
        "total_cache_create_tokens": 100,
        "total_cost_usd": 0.05,
    }
    messages = [
        {
            "timestamp": "2026-02-20T10:00:05Z",
            "role": "assistant",
            "model": "claude-sonnet-4-6",
            "input_tokens": 1500,
            "output_tokens": 200,
            "cost_usd": 0.01,
            "tool_names": "Read",
        }
    ]
    panel = format_telemetry(session, messages)
    assert panel.title == "Telemetry"


def test_format_survey_results():
    response = {
        "survey_id": "survey-1",
        "timestamp": "2026-02-20T10:05:00Z",
        "answers": '{"human-est": 3.5}',
        "notes": "test notes",
    }
    outputs = [{"output_id": "human-est", "uplift_factor": 3.5}]
    panel = format_survey_results(response, outputs)
    assert panel.title == "Survey Results"


def test_format_survey_results_dict_answers():
    response = {
        "survey_id": "survey-1",
        "timestamp": "2026-02-20T10:05:00Z",
        "answers": {"human-est": 3.5},
        "notes": "",
    }
    outputs = []
    panel = format_survey_results(response, outputs)
    assert panel.title == "Survey Results"


def test_format_transcript_raw():
    panel = format_transcript("Some transcript text", compacted=False)
    assert panel.title == "Transcript"


def test_format_transcript_compacted():
    panel = format_transcript("## ACTIONS\nDid stuff.\n## OUTCOME\nSuccess.", compacted=True)
    assert panel.title == "Compacted Transcript"


def test_format_judge_results():
    result = {
        "success": True,
        "tasks": [
            {"description": "Fix login bug", "succeeded": True, "estimated_minutes_without_ai": 30},
            {"description": "Broken refactor", "succeeded": False, "estimated_minutes_without_ai": 0},
        ],
        "total_minutes_without_ai": 30,
        "confidence": "medium",
        "reasoning": "Simple bug fix",
        "model": "claude-sonnet-4-6",
        "cost_usd": 0.006,
    }
    panel = format_judge_results(result)
    assert panel.title == "LLM Judge Results"


def test_format_judge_results_with_uplift():
    result = {
        "success": True,
        "tasks": [{"description": "Fix bug", "succeeded": True, "estimated_minutes_without_ai": 30}],
        "total_minutes_without_ai": 30,
        "confidence": "medium",
        "reasoning": "Bug fix",
        "model": "claude-sonnet-4-6",
        "cost_usd": 0.006,
    }
    time_data = {"active_minutes": 10, "active_windows": 1}
    panel = format_judge_results(result, time_data)
    assert panel.title == "LLM Judge Results"


def test_format_judge_results_no_tasks():
    result = {
        "success": False,
        "tasks": [],
        "total_minutes_without_ai": 0,
        "confidence": "low",
    }
    panel = format_judge_results(result)
    assert panel.title == "LLM Judge Results"
