"""Tests for the sessions and show CLI commands."""

import json

from click.testing import CliRunner

from open_uplift.cli.commands import cli


def test_sessions_empty_db(db, cli_runner, monkeypatch):
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, ["sessions", "list", "--search", "anything"])
    assert result.exit_code == 0
    assert "No sessions found" in result.output


def test_sessions_search(db, cli_runner, monkeypatch, sample_session):
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, ["sessions", "list", "--search", "myproject"])
    assert result.exit_code == 0
    assert "myproject" in result.output


def test_sessions_project_filter(db, cli_runner, monkeypatch, sample_session):
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, ["sessions", "list", "--project", "myproject"])
    assert result.exit_code == 0
    assert "myproject" in result.output


def test_sessions_project_filter_no_match(db, cli_runner, monkeypatch, sample_session):
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, ["sessions", "list", "--project", "nonexistent"])
    assert result.exit_code == 0
    assert "No sessions found" in result.output


def test_sessions_show_all(db, cli_runner, monkeypatch, sample_session):
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, ["sessions", "list", "--all"])
    assert result.exit_code == 0
    assert "myproj" in result.output  # may be truncated in narrow table columns


def test_show_basic(db, cli_runner, monkeypatch, sample_session):
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, ["sessions", "show", sample_session])
    assert result.exit_code == 0
    assert "Session Detail" in result.output
    assert "myproject" in result.output


def test_show_not_found(db, cli_runner, monkeypatch):
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, ["sessions", "show", "nonexistent-id"])
    assert result.exit_code == 0
    assert "not found" in result.output


def test_show_telemetry(db, cli_runner, monkeypatch, sample_session):
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, ["sessions", "show", sample_session, "--telemetry"])
    assert result.exit_code == 0
    assert "Telemetry" in result.output


def test_show_survey(db, cli_runner, monkeypatch, sample_session_with_results):
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, ["sessions", "show", sample_session_with_results, "--survey"])
    assert result.exit_code == 0
    assert "Survey Results" in result.output


def test_show_judge(db, cli_runner, monkeypatch, sample_session_with_results):
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, ["sessions", "show", sample_session_with_results, "--judge"])
    assert result.exit_code == 0
    assert "LLM Judge Results" in result.output


def test_show_all_flags(db, cli_runner, monkeypatch, sample_session_with_results):
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, ["sessions", "show", sample_session_with_results, "--all"])
    assert result.exit_code == 0
    assert "Session Detail" in result.output
    assert "Telemetry" in result.output
    assert "Survey Results" in result.output
    assert "LLM Judge Results" in result.output


def test_show_no_survey(db, cli_runner, monkeypatch, sample_session):
    """--all on a session without survey shows 'No survey response'."""
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, ["sessions", "show", sample_session, "--all"])
    assert result.exit_code == 0
    assert "No survey response" in result.output


def test_show_backward_compat(db, cli_runner, monkeypatch, sample_session):
    """The old 'show' top-level command still works via hidden alias."""
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, ["show", sample_session])
    assert result.exit_code == 0
    assert "Session Detail" in result.output


def test_show_default_includes_survey_and_judge(db, cli_runner, monkeypatch, sample_session_with_results):
    """With no flags, show displays survey and judge by default."""
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, ["sessions", "show", sample_session_with_results])
    assert result.exit_code == 0
    assert "Session Detail" in result.output
    assert "Survey Results" in result.output
    assert "LLM Judge Results" in result.output
    # Should NOT show telemetry or transcript by default
    assert "Telemetry" not in result.output


def test_show_default_no_survey_message(db, cli_runner, monkeypatch, sample_session):
    """With no flags on a session without survey, shows 'No survey response'."""
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, ["sessions", "show", sample_session])
    assert result.exit_code == 0
    assert "No survey response" in result.output
    assert "No LLM judge" in result.output


def test_show_prefix_match(db, cli_runner, monkeypatch, sample_session):
    """Show accepts a prefix of the session ID."""
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    prefix = sample_session[:12]
    result = cli_runner.invoke(cli, ["sessions", "show", prefix])
    assert result.exit_code == 0
    assert "Session Detail" in result.output
    assert "myproject" in result.output


def test_show_prefix_ambiguous(db, cli_runner, monkeypatch, sample_session, sample_session_with_results):
    """Ambiguous prefix shows error (both sessions start with 'test-session')."""
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    # sample_session_with_results uses the same session_id as sample_session,
    # so we need a second distinct session for this test
    from datetime import datetime, timezone
    db.execute(
        """INSERT INTO sessions
           (session_id, tool_source, project_path, project_name, started_at,
            message_count, total_cost_usd, model_primary, scaffold)
           VALUES ('test-session-aaaa', 'claude_code', '/tmp', 'other',
                   '2026-02-20T10:00:00Z', 1, 0.01, 'claude-sonnet-4-6', 'claude_code')"""
    )
    db.commit()
    result = cli_runner.invoke(cli, ["sessions", "show", "test-session"])
    assert result.exit_code == 0
    assert "Ambiguous" in result.output


def test_sessions_list_shows_uplift(db, cli_runner, monkeypatch, sample_session_with_results, sample_uplift_data):
    """Sessions list table shows uplift factor when available."""
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, ["sessions", "list", "--all"])
    assert result.exit_code == 0
    assert "Uplift" in result.output  # column header present


def test_sessions_list_shows_model(db, cli_runner, monkeypatch, sample_session):
    """Sessions list table shows model column."""
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, ["sessions", "list", "--all"])
    assert result.exit_code == 0
    assert "Model" in result.output  # column header present
    assert "sonne" in result.output  # truncated "sonnet-4-6"
