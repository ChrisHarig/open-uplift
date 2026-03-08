"""Tests for the CLI export command."""

import csv
import io
import json
import os

from click.testing import CliRunner

from open_uplift.cli.commands import cli


def test_export_csv_stdout(db, cli_runner, monkeypatch, sample_session):
    """CSV export to stdout."""
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, ["sessions", "export", "--format", "csv"])
    assert result.exit_code == 0
    reader = csv.DictReader(io.StringIO(result.output))
    rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["session_id"] == sample_session


def test_export_json_stdout(db, cli_runner, monkeypatch, sample_session):
    """JSON export to stdout."""
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, ["sessions", "export", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["session_id"] == sample_session


def test_export_to_file(db, cli_runner, monkeypatch, sample_session, tmp_path):
    """--output writes file."""
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    output_file = str(tmp_path / "test.csv")
    result = cli_runner.invoke(cli, ["sessions", "export", "--format", "csv", "-o", output_file])
    assert result.exit_code == 0
    assert "Exported 1 sessions" in result.output
    assert os.path.exists(output_file)
    with open(output_file) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == 1


def test_export_with_project_filter(db, cli_runner, monkeypatch, sample_session):
    """--project filter works."""
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)

    result = cli_runner.invoke(cli, ["sessions", "export", "--format", "json", "--project", "myproject"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1

    result = cli_runner.invoke(cli, ["sessions", "export", "--format", "json", "--project", "nonexistent"])
    assert result.exit_code == 0
    assert "No sessions found" in result.output


def test_export_include_all(db, cli_runner, monkeypatch, sample_session_with_results):
    """--include-all includes all data sections."""
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, ["sessions", "export", "--format", "json", "--include-all"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    row = data[0]
    assert "survey_human_est" in row
    assert "judge_success" in row
    assert "compacted_transcript" in row
    assert "telemetry_messages" in row


def test_export_no_sessions(db, cli_runner, monkeypatch):
    """Graceful empty output when no sessions exist."""
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, ["sessions", "export"])
    assert result.exit_code == 0
    assert "No sessions found" in result.output
