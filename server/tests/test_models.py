"""Tests for Pydantic data models."""

import pytest
from pydantic import ValidationError

from open_uplift.models import MessageData, SelfReport, SessionData

pytestmark = pytest.mark.smoke


def test_self_report_defaults():
    r = SelfReport()
    assert r.tool_source == "claude_code"
    assert r.speedup_factor is None
    assert r.session_id is None


def test_self_report_speedup_bounds():
    r = SelfReport(speedup_factor=5.0)
    assert r.speedup_factor == 5.0

    with pytest.raises(ValidationError):
        SelfReport(speedup_factor=0.05)  # below 0.1

    with pytest.raises(ValidationError):
        SelfReport(speedup_factor=200.0)  # above 100


def test_message_data_required_fields():
    m = MessageData(session_id="s1", timestamp="2026-01-01T00:00:00Z", role="user")
    assert m.session_id == "s1"
    assert m.input_tokens == 0
    assert m.cost_usd == 0.0


def test_message_data_with_tokens():
    m = MessageData(
        session_id="s1",
        timestamp="2026-01-01T00:00:00Z",
        role="assistant",
        model="claude-sonnet-4-6",
        input_tokens=1000,
        output_tokens=200,
        cache_read_tokens=500,
        cost_usd=0.01,
    )
    assert m.model == "claude-sonnet-4-6"
    assert m.input_tokens == 1000


def test_session_data_defaults():
    s = SessionData(session_id="s1")
    assert s.tool_source == "claude_code"
    assert s.total_input_tokens == 0
    assert s.total_cost_usd == 0.0
    assert s.message_count == 0


def test_session_data_serialization():
    s = SessionData(
        session_id="s1",
        project_name="myproject",
        started_at="2026-01-01T00:00:00Z",
        total_input_tokens=5000,
        total_output_tokens=1000,
        total_cost_usd=0.03,
        message_count=10,
        tool_call_count=5,
        model_primary="claude-sonnet-4-6",
    )
    d = s.model_dump()
    assert d["session_id"] == "s1"
    assert d["total_input_tokens"] == 5000
    assert d["model_primary"] == "claude-sonnet-4-6"


def test_session_data_from_dict():
    d = {
        "session_id": "s2",
        "project_path": "/home/user/project",
        "project_name": "project",
        "started_at": "2026-01-01T00:00:00Z",
    }
    s = SessionData(**d)
    assert s.session_id == "s2"
    assert s.project_path == "/home/user/project"
