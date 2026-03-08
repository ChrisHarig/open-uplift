"""Tests for the enhanced survey CLI command."""

import json

from click.testing import CliRunner

from open_uplift.cli.commands import cli
from open_uplift.surveys import delete_survey_response


def test_delete_survey_response(db, sample_session):
    """Test deleting a survey response and its outputs."""
    # Create a response
    db.execute(
        """INSERT INTO survey_responses
           (session_id, survey_id, tool_source, timestamp, answers, notes)
           VALUES (?, 'survey-1', 'claude_code', '2026-02-20T10:00:00Z', '{"human-est": 3.5}', '')""",
        (sample_session,),
    )
    resp_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.execute(
        """INSERT INTO uplift_outputs
           (survey_response_id, output_id, uplift_factor, metadata, timestamp)
           VALUES (?, 'human-est', 3.5, '{}', '2026-02-20T10:00:00Z')""",
        (resp_id,),
    )
    db.commit()

    # Verify it exists
    assert db.execute("SELECT COUNT(*) FROM survey_responses WHERE session_id = ?", (sample_session,)).fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM uplift_outputs WHERE survey_response_id = ?", (resp_id,)).fetchone()[0] == 1

    # Delete it
    result = delete_survey_response(db, sample_session, "survey-1")
    assert result is True

    # Verify deletion
    assert db.execute("SELECT COUNT(*) FROM survey_responses WHERE session_id = ?", (sample_session,)).fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM uplift_outputs WHERE survey_response_id = ?", (resp_id,)).fetchone()[0] == 0


def test_delete_survey_response_not_found(db, sample_session):
    """Deleting non-existent response returns False."""
    result = delete_survey_response(db, sample_session, "survey-1")
    assert result is False


def test_survey_no_session_selected(db, cli_runner, monkeypatch):
    """Survey with no sessions available."""
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    monkeypatch.setattr("open_uplift.cli.commands._pick_session", lambda: None)
    result = cli_runner.invoke(cli, ["sessions", "survey"])
    assert result.exit_code == 0
    assert "No session selected" in result.output


def test_survey_force_flag_passes_to_run_survey(db, cli_runner, monkeypatch, sample_session):
    """The --force flag is passed through to run_survey."""
    captured = {}

    def mock_run_survey(session_id, force=False):
        captured["session_id"] = session_id
        captured["force"] = force

    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    monkeypatch.setattr("open_uplift.cli.survey.run_survey", mock_run_survey)
    result = cli_runner.invoke(cli, ["sessions", "survey", "--session-id", sample_session, "--force"])
    assert result.exit_code == 0
    assert captured.get("force") is True


def test_survey_existing_response_shown(db, sample_session_with_results, monkeypatch):
    """When a response exists, it should be displayed."""
    from open_uplift.cli.survey import _show_existing_response

    has_existing = _show_existing_response(db, sample_session_with_results, "survey-1")
    assert has_existing is True


def test_survey_no_existing_response(db, sample_session, monkeypatch):
    """When no response exists, returns False."""
    from open_uplift.cli.survey import _show_existing_response

    has_existing = _show_existing_response(db, sample_session, "survey-1")
    assert has_existing is False


def test_survey_backward_compat(db, cli_runner, monkeypatch):
    """The old 'survey' top-level command still works via hidden alias."""
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    monkeypatch.setattr("open_uplift.cli.commands._pick_session", lambda: None)
    result = cli_runner.invoke(cli, ["survey"])
    assert result.exit_code == 0
    assert "No session selected" in result.output
