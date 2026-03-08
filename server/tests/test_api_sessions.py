"""Integration tests for session API endpoints."""

import json

import pytest


def test_health(app):
    resp = app.get("/api/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_get_sessions_empty(app):
    resp = app.get("/api/sessions")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["sessions"] == []
    assert data["total"] == 0


def test_get_sessions_with_data(app, sample_session):
    resp = app.get("/api/sessions")
    data = resp.get_json()
    assert data["total"] == 1
    assert len(data["sessions"]) == 1
    assert data["sessions"][0]["session_id"] == sample_session


def test_get_sessions_limit_offset(app, sample_session):
    resp = app.get("/api/sessions?limit=10&offset=0")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 1


def test_get_sessions_filter_model(app, sample_session):
    resp = app.get("/api/sessions?model=claude-sonnet-4-6")
    data = resp.get_json()
    assert data["total"] == 1

    resp = app.get("/api/sessions?model=nonexistent-model")
    data = resp.get_json()
    assert data["total"] == 0


def test_get_sessions_filter_date(app, sample_session):
    resp = app.get("/api/sessions?date_from=2026-02-20&date_to=2026-02-20")
    data = resp.get_json()
    assert data["total"] == 1

    resp = app.get("/api/sessions?date_from=2099-01-01")
    data = resp.get_json()
    assert data["total"] == 0


def test_get_sessions_filter_scaffold(app, sample_session):
    resp = app.get("/api/sessions?scaffold=claude_code")
    data = resp.get_json()
    assert data["total"] == 1


def test_get_sessions_filter_has_survey(app, sample_session, db):
    # No survey yet
    resp = app.get("/api/sessions?has_survey=false")
    assert resp.get_json()["total"] == 1

    resp = app.get("/api/sessions?has_survey=true")
    assert resp.get_json()["total"] == 0

    # Add survey
    from open_uplift.surveys import submit_survey_response
    submit_survey_response(db, sample_session, "survey-1", {"human-est": 3.0})
    db.commit()

    resp = app.get("/api/sessions?has_survey=true")
    assert resp.get_json()["total"] == 1


def test_get_sessions_filter_has_judge(app, sample_session, db):
    resp = app.get("/api/sessions?has_judge=false")
    assert resp.get_json()["total"] == 1

    # Add judge result
    db.execute(
        """INSERT INTO script_results
           (session_id, script_id, status, started_at, completed_at)
           VALUES (?, 'llm-time-estimate', 'completed', '2026-01-01', '2026-01-01')""",
        (sample_session,),
    )
    db.commit()

    resp = app.get("/api/sessions?has_judge=true")
    assert resp.get_json()["total"] == 1


def test_get_sessions_filter_has_compaction(app, sample_session, db):
    resp = app.get("/api/sessions?has_compaction=false")
    assert resp.get_json()["total"] == 1

    db.execute(
        """INSERT INTO script_results
           (session_id, script_id, status, started_at, completed_at)
           VALUES (?, 'transcript-compact', 'completed', '2026-01-01', '2026-01-01')""",
        (sample_session,),
    )
    db.commit()

    resp = app.get("/api/sessions?has_compaction=true")
    assert resp.get_json()["total"] == 1


def test_session_detail(app, sample_session):
    resp = app.get(f"/api/sessions/{sample_session}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["session"]["session_id"] == sample_session
    assert len(data["messages"]) >= 1


def test_session_detail_not_found(app):
    resp = app.get("/api/sessions/nonexistent")
    assert resp.status_code == 404


def test_filter_options(app, sample_session):
    resp = app.get("/api/sessions/filter-options")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "models" in data
    assert "scaffolds" in data
    assert "projects" in data
    assert "claude-sonnet-4-6" in data["models"]
