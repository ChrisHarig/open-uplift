"""Tests for the polished run CLI command."""

import json

from click.testing import CliRunner

from open_uplift.cli.commands import cli


def test_run_dry_run_single(db, cli_runner, monkeypatch, sample_session):
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, [
        "sessions", "run", "transcript-compact", "--session-id", sample_session, "--dry-run",
    ])
    assert result.exit_code == 0
    assert "Dry run" in result.output
    assert sample_session[:12] in result.output


def test_run_dry_run_all(db, cli_runner, monkeypatch, sample_session):
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, [
        "sessions", "run", "transcript-compact", "--all", "--dry-run",
    ])
    assert result.exit_code == 0
    assert "Dry run" in result.output
    assert "1 sessions" in result.output


def test_run_no_session_selected(db, cli_runner, monkeypatch):
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    monkeypatch.setattr("open_uplift.cli.commands._pick_session", lambda: None)
    result = cli_runner.invoke(cli, ["sessions", "run", "transcript-compact"])
    assert result.exit_code == 0
    assert "No session selected" in result.output


def test_run_single_session_error(db, cli_runner, monkeypatch, sample_session):
    """Run on a session without a transcript file produces an error."""
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, [
        "sessions", "run", "transcript-compact", "--session-id", sample_session,
    ])
    assert result.exit_code == 0
    assert "Error" in result.output or "error" in result.output.lower()


def test_run_single_session_success(db, cli_runner, monkeypatch, sample_session, mock_llm, tmp_path):
    """Run transcript-compact with a mock transcript file."""
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    monkeypatch.setattr("open_uplift.scripts.get_api_key", lambda db, provider, name="default": "fake-key")

    # Create a minimal transcript file and register in ingest_log
    transcript_path = tmp_path / f"{sample_session}.jsonl"
    entry = {
        "type": "conversation",
        "message": {"role": "user", "content": "Hello"},
        "timestamp": "2026-02-20T10:00:00Z",
    }
    transcript_path.write_text(json.dumps(entry) + "\n")
    db.execute(
        "INSERT INTO ingest_log (file_path, byte_offset, last_synced) VALUES (?, 0, '2026-02-20T10:00:00Z')",
        (str(transcript_path),),
    )
    db.commit()

    result = cli_runner.invoke(cli, [
        "sessions", "run", "transcript-compact", "--session-id", sample_session,
    ])
    assert result.exit_code == 0
    assert "Compacted Transcript" in result.output or "Done" in result.output


def test_run_all_empty(db, cli_runner, monkeypatch, sample_session_with_results):
    """Run --all when all sessions already have results shows 0 sessions."""
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, [
        "sessions", "run", "transcript-compact", "--all",
    ])
    assert result.exit_code == 0
    assert "0 sessions" in result.output or "succeeded" in result.output


def test_run_script_backward_compat(db, cli_runner, monkeypatch, sample_session):
    """The run-script alias still works."""
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, [
        "run-script", "transcript-compact", "--session-id", sample_session, "--dry-run",
    ])
    assert result.exit_code == 0
    assert "Dry run" in result.output
