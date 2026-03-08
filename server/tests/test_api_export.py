"""Tests for the API export endpoint."""

import csv
import io
import json

import pytest


def test_export_csv_with_data(app, sample_session):
    """CSV export returns correct content type, disposition, and parseable body."""
    resp = app.get("/api/sessions/export?format=csv")
    assert resp.status_code == 200
    assert resp.content_type == "text/csv; charset=utf-8"
    assert "Content-Disposition" in resp.headers
    assert "attachment" in resp.headers["Content-Disposition"]
    assert ".csv" in resp.headers["Content-Disposition"]

    reader = csv.DictReader(io.StringIO(resp.data.decode()))
    rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["session_id"] == sample_session


def test_export_json_with_data(app, sample_session):
    """JSON export returns correct content type and parseable body."""
    resp = app.get("/api/sessions/export?format=json")
    assert resp.status_code == 200
    assert "application/json" in resp.content_type
    assert "Content-Disposition" in resp.headers
    assert ".json" in resp.headers["Content-Disposition"]

    data = json.loads(resp.data.decode())
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["session_id"] == sample_session


def test_export_invalid_format(app, sample_session):
    """Invalid format returns 400."""
    resp = app.get("/api/sessions/export?format=xml")
    assert resp.status_code == 400


def test_export_respects_filters(app, sample_session):
    """Project filter limits results."""
    resp = app.get("/api/sessions/export?format=json&project=myproject")
    data = json.loads(resp.data.decode())
    assert len(data) == 1

    resp = app.get("/api/sessions/export?format=json&project=nonexistent")
    data = json.loads(resp.data.decode())
    assert len(data) == 0


def test_export_selected_session_ids(app, sample_session):
    """session_ids param exports specific sessions."""
    resp = app.get(f"/api/sessions/export?format=json&session_ids={sample_session}")
    data = json.loads(resp.data.decode())
    assert len(data) == 1
    assert data[0]["session_id"] == sample_session

    resp = app.get("/api/sessions/export?format=json&session_ids=nonexistent")
    data = json.loads(resp.data.decode())
    assert len(data) == 0


def test_export_csv_empty(app):
    """Empty export returns empty CSV."""
    resp = app.get("/api/sessions/export?format=csv")
    assert resp.status_code == 200
    assert resp.data.decode().strip() == ""


def test_export_with_include_flags(app, sample_session_with_results):
    """Include flags add extra data."""
    resp = app.get("/api/sessions/export?format=json&include_judge=true&include_survey=true")
    data = json.loads(resp.data.decode())
    assert len(data) == 1
    assert "judge_success" in data[0]
    assert "survey_human_est" in data[0]


def test_export_date_filter(app, sample_session):
    """Date filters work on export."""
    resp = app.get("/api/sessions/export?format=json&date_from=2026-02-20&date_to=2026-02-20")
    data = json.loads(resp.data.decode())
    assert len(data) == 1

    resp = app.get("/api/sessions/export?format=json&date_from=2099-01-01")
    data = json.loads(resp.data.decode())
    assert len(data) == 0
