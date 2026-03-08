"""Tests for the config CLI commands with nested sub-groups."""

import json

from click.testing import CliRunner

from open_uplift.cli.commands import cli


def test_explain_command(cli_runner):
    """The explain command prints help panels and exits cleanly."""
    result = cli_runner.invoke(cli, ["explain"])
    assert result.exit_code == 0
    assert "What is Open Uplift?" in result.output
    assert "Setup Guide" in result.output
    assert "Command Tree" in result.output
    assert "open-uplift" in result.output


def test_config_scripts_list_prompts(db, cli_runner, monkeypatch):
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, ["config", "scripts", "list-prompts"])
    assert result.exit_code == 0
    assert "compaction-default" in result.output
    assert "judge-default" in result.output


def test_config_scripts_list_prompts_detail(db, cli_runner, monkeypatch):
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, ["config", "scripts", "list-prompts", "judge-default"])
    assert result.exit_code == 0
    assert "judge-default" in result.output
    assert "System Prompt" in result.output


def test_config_scripts_show(db, cli_runner, monkeypatch):
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, ["config", "scripts", "show"])
    assert result.exit_code == 0
    assert "anthropic" in result.output
    assert "Script Configuration" in result.output


def test_config_scripts_set_judge_model(db, cli_runner, monkeypatch):
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, [
        "config", "scripts", "set", "--judge-model", "gpt-4o",
    ])
    assert result.exit_code == 0
    assert "updated" in result.output

    # Verify persistence in nested format
    row = db.execute("SELECT value FROM config WHERE key = 'script_config'").fetchone()
    config = json.loads(row["value"])
    assert config["judge"]["model"] == "gpt-4o"


def test_config_scripts_set_compaction_provider(db, cli_runner, monkeypatch):
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, [
        "config", "scripts", "set", "--compaction-provider", "openai",
    ])
    assert result.exit_code == 0
    assert "updated" in result.output


def test_config_questions_add_flags(db, cli_runner, monkeypatch):
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, [
        "config", "questions", "add",
        "--id", "test-q",
        "--label", "Test question?",
        "--type", "number",
        "--min", "1",
        "--max", "100",
        "--description", "A test question",
    ])
    assert result.exit_code == 0
    assert "test-q" in result.output
    assert "added" in result.output

    # Verify persistence
    from open_uplift.surveys import get_questions
    questions = get_questions(db)
    assert "test-q" in questions
    assert questions["test-q"]["label"] == "Test question?"
    assert questions["test-q"]["validation"]["min"] == 1.0


def test_config_surveys_add_flags(db, cli_runner, monkeypatch):
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, [
        "config", "surveys", "add",
        "--name", "Test Survey",
        "--description", "A test survey",
        "--questions", "human-est",
    ])
    assert result.exit_code == 0
    assert "added" in result.output

    # Verify persistence
    from open_uplift.surveys import get_surveys
    surveys = get_surveys(db)
    assert "test-survey" in surveys
    assert surveys["test-survey"]["questions"] == ["human-est"]


def test_config_surveys_add_unknown_question(db, cli_runner, monkeypatch):
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, [
        "config", "surveys", "add",
        "--name", "Bad Survey",
        "--description", "Bad",
        "--questions", "nonexistent",
    ])
    assert result.exit_code == 0
    assert "Unknown question" in result.output


def test_config_scripts_edit_prompt_not_found(db, cli_runner, monkeypatch):
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, ["config", "scripts", "edit-prompt", "nonexistent"])
    assert result.exit_code == 0
    assert "not found" in result.output


def test_config_existing_commands_still_work(db, cli_runner, monkeypatch):
    """Verify old flat config command paths still work via hidden aliases."""
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)

    # show-active (alias for surveys show-active)
    result = cli_runner.invoke(cli, ["config", "show-active"])
    assert result.exit_code == 0
    assert "default" in result.output

    # list-surveys (alias for surveys list)
    result = cli_runner.invoke(cli, ["config", "list-surveys"])
    assert result.exit_code == 0
    assert "default" in result.output

    # list-questions (alias for questions list)
    result = cli_runner.invoke(cli, ["config", "list-questions"])
    assert result.exit_code == 0
    assert "human-est" in result.output

    # set-active (alias for surveys set-active)
    result = cli_runner.invoke(cli, ["config", "set-active", "survey-2"])
    assert result.exit_code == 0
    assert "survey-2" in result.output

    # show-llm-config (alias for scripts show)
    result = cli_runner.invoke(cli, ["config", "show-llm-config"])
    assert result.exit_code == 0
    assert "Script Configuration" in result.output

    # show-prompts (alias for scripts list-prompts)
    result = cli_runner.invoke(cli, ["config", "show-prompts"])
    assert result.exit_code == 0
    assert "compaction-default" in result.output

    # run-modes (hidden alias for batch-sync)
    result = cli_runner.invoke(cli, ["config", "run-modes"])
    assert result.exit_code == 0
    assert "Batch Sync Configuration" in result.output


def test_config_batch_sync_show(db, cli_runner, monkeypatch):
    """Bare `config batch-sync` shows current config panel."""
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, ["config", "batch-sync"])
    assert result.exit_code == 0
    assert "Batch Sync Configuration" in result.output
    assert "Disabled" in result.output


def test_config_batch_sync_set_enable(db, cli_runner, monkeypatch):
    """Set start hour and frequency enables batch sync."""
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    # Stub update_scheduler_config to avoid starting real timers
    monkeypatch.setattr("open_uplift.job_queue.update_scheduler_config", lambda: None)
    result = cli_runner.invoke(cli, [
        "config", "batch-sync", "set", "--start-hour", "3", "--frequency", "12",
    ])
    assert result.exit_code == 0
    assert "enabled" in result.output.lower()
    assert "12" in result.output
    assert "03:00" in result.output

    # Verify persistence
    row = db.execute("SELECT value FROM config WHERE key = 'run_mode_config'").fetchone()
    config = json.loads(row["value"])
    assert config["enabled"] is True
    assert config["start_hour"] == 3
    assert config["frequency_hours"] == 12.0


def test_config_batch_sync_set_off(db, cli_runner, monkeypatch):
    """--off disables batch sync."""
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    monkeypatch.setattr("open_uplift.job_queue.update_scheduler_config", lambda: None)
    result = cli_runner.invoke(cli, ["config", "batch-sync", "set", "--off"])
    assert result.exit_code == 0
    assert "disabled" in result.output.lower()


def test_config_batch_sync_set_noop(db, cli_runner, monkeypatch):
    """No flags gives an error message."""
    monkeypatch.setattr("open_uplift.cli.commands.init_db", lambda: None)
    result = cli_runner.invoke(cli, ["config", "batch-sync", "set"])
    assert result.exit_code == 0
    assert "Nothing to update" in result.output
