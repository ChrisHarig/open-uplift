"""Integration tests for survey API endpoints."""

import json

import pytest


def test_get_survey_responses_empty(app):
    resp = app.get("/api/survey-responses")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) == 0


def test_submit_survey_response(app, sample_session):
    resp = app.post(
        "/api/survey-responses",
        json={
            "session_id": sample_session,
            "survey_id": "default",
            "answers": {"human-est": 3.5},
            "notes": "Test",
        },
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["id"] > 0
    assert len(data["outputs"]) == 1


def test_submit_duplicate_survey_response(app, sample_session):
    app.post(
        "/api/survey-responses",
        json={
            "session_id": sample_session,
            "survey_id": "default",
            "answers": {"human-est": 3.5},
        },
    )
    resp = app.post(
        "/api/survey-responses",
        json={
            "session_id": sample_session,
            "survey_id": "default",
            "answers": {"human-est": 4.0},
        },
    )
    assert resp.status_code == 409


def test_get_survey_responses_after_submit(app, sample_session):
    app.post(
        "/api/survey-responses",
        json={
            "session_id": sample_session,
            "survey_id": "default",
            "answers": {"human-est": 2.0},
        },
    )
    resp = app.get("/api/survey-responses")
    data = resp.get_json()
    assert len(data) == 1


def test_get_surveys(app):
    resp = app.get("/api/surveys")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "surveys" in data
    assert "active" in data


def test_get_active_survey(app):
    resp = app.get("/api/surveys/active")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "survey" in data
    assert data["survey"]["id"] == "default"
    assert "questions" in data["survey"]


def test_set_active_survey(app):
    # "default" is the only seeded survey, so set it again to verify the endpoint works
    resp = app.put(
        "/api/surveys/active",
        json={"survey_id": "default"},
    )
    assert resp.status_code == 200

    resp = app.get("/api/surveys/active")
    assert resp.get_json()["survey"]["id"] == "default"


def test_set_active_survey_invalid(app):
    resp = app.put(
        "/api/surveys/active",
        json={"survey_id": "nonexistent"},
    )
    assert resp.status_code == 404
