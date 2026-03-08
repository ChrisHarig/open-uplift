"""Tests for the export module (build_export_rows, format_csv, format_json)."""

import csv
import io
import json

import pytest


def test_build_export_rows_core_only(db, sample_session):
    """Core fields present without include flags."""
    from open_uplift.cli.export import build_export_rows

    rows = build_export_rows(db)
    assert len(rows) == 1
    row = rows[0]
    assert row["session_id"] == sample_session
    assert row["project_name"] == "myproject"
    assert row["model_primary"] == "claude-sonnet-4-6"
    assert row["message_count"] == 5
    assert row["tool_call_count"] == 3
    assert row["total_input_tokens"] == 12500
    assert row["total_output_tokens"] == 780
    # No optional fields
    assert "survey_human_est" not in row
    assert "judge_success" not in row
    assert "compacted_transcript" not in row
    assert "telemetry_messages" not in row


def test_build_export_rows_with_survey(db, sample_session_with_results):
    """Survey data included when flag set."""
    from open_uplift.cli.export import build_export_rows

    rows = build_export_rows(db, include_survey=True)
    assert len(rows) == 1
    row = rows[0]
    assert "survey_human_est" in row
    assert row["survey_human_est"] == 3.5
    assert row["survey_notes"] == "test notes"


def test_build_export_rows_with_judge(db, sample_session_with_results, sample_uplift_data):
    """Judge data included when flag set."""
    from open_uplift.cli.export import build_export_rows

    rows = build_export_rows(db, include_judge=True)
    assert len(rows) >= 1
    # Find our session with judge data
    judged = [r for r in rows if r["judge_success"] is not None]
    assert len(judged) > 0
    row = judged[0]
    assert row["judge_success"] == "true"
    assert "judge_confidence" in row
    assert "judge_reasoning" in row
    assert "judge_tasks" in row


def test_build_export_rows_with_transcript(db, sample_session_with_results):
    """Transcript data included when flag set."""
    from open_uplift.cli.export import build_export_rows

    rows = build_export_rows(db, include_transcript=True)
    assert len(rows) == 1
    row = rows[0]
    assert "compacted_transcript" in row
    assert "ACTIONS" in row["compacted_transcript"]


def test_build_export_rows_with_telemetry(db, sample_session):
    """Telemetry data included when flag set."""
    from open_uplift.cli.export import build_export_rows

    rows = build_export_rows(db, include_telemetry=True)
    assert len(rows) == 1
    row = rows[0]
    assert "telemetry_messages" in row
    assert len(row["telemetry_messages"]) == 5
    assert row["telemetry_messages"][0]["role"] == "user"


def test_build_export_rows_with_session_ids(db, sample_session):
    """Filter by specific session IDs."""
    from open_uplift.cli.export import build_export_rows

    rows = build_export_rows(db, session_ids=[sample_session])
    assert len(rows) == 1
    assert rows[0]["session_id"] == sample_session

    rows = build_export_rows(db, session_ids=["nonexistent"])
    assert len(rows) == 0


def test_build_export_rows_with_conditions(db, sample_session):
    """Filter by SQL conditions."""
    from open_uplift.cli.export import build_export_rows

    rows = build_export_rows(db, conditions=["s.project_name = ?"], params=["myproject"])
    assert len(rows) == 1

    rows = build_export_rows(db, conditions=["s.project_name = ?"], params=["nonexistent"])
    assert len(rows) == 0


def test_build_export_rows_with_limit(db, sample_session_with_results, sample_uplift_data):
    """Limit works."""
    from open_uplift.cli.export import build_export_rows

    all_rows = build_export_rows(db)
    assert len(all_rows) >= 2

    limited = build_export_rows(db, limit=1)
    assert len(limited) == 1


def test_format_csv_basic(db, sample_session):
    """CSV output is parseable with correct headers."""
    from open_uplift.cli.export import build_export_rows, format_csv

    rows = build_export_rows(db)
    output = format_csv(rows)
    assert output

    reader = csv.DictReader(io.StringIO(output))
    parsed = list(reader)
    assert len(parsed) == 1
    assert parsed[0]["session_id"] == sample_session
    assert parsed[0]["project_name"] == "myproject"


def test_format_csv_handles_json_fields(db, sample_session):
    """JSON array fields are serialized properly in CSV."""
    from open_uplift.cli.export import build_export_rows, format_csv

    rows = build_export_rows(db, include_telemetry=True)
    output = format_csv(rows)

    reader = csv.DictReader(io.StringIO(output))
    parsed = list(reader)
    # telemetry_messages should be a JSON string
    telemetry = json.loads(parsed[0]["telemetry_messages"])
    assert isinstance(telemetry, list)
    assert len(telemetry) == 5


def test_format_csv_empty():
    """Empty rows produce empty string."""
    from open_uplift.cli.export import format_csv

    assert format_csv([]) == ""


def test_format_json_basic(db, sample_session):
    """JSON output is valid with correct structure."""
    from open_uplift.cli.export import build_export_rows, format_json

    rows = build_export_rows(db)
    output = format_json(rows)
    parsed = json.loads(output)
    assert isinstance(parsed, list)
    assert len(parsed) == 1
    assert parsed[0]["session_id"] == sample_session


def test_format_json_with_telemetry(db, sample_session):
    """JSON output preserves nested structures."""
    from open_uplift.cli.export import build_export_rows, format_json

    rows = build_export_rows(db, include_telemetry=True)
    output = format_json(rows)
    parsed = json.loads(output)
    assert isinstance(parsed[0]["telemetry_messages"], list)
    assert len(parsed[0]["telemetry_messages"]) == 5
