"""Integration tests for script execution API endpoints."""

import json

import pytest


def test_run_script_missing_fields(app):
    resp = app.post("/api/scripts/run", json={})
    assert resp.status_code == 400


def test_run_script_unknown_script(app, sample_session, db):
    """Unknown script_id raises ValueError."""
    from open_uplift.keystore import store_api_key
    store_api_key(db, "anthropic", "default", "dummy-key")

    with pytest.raises(ValueError, match="Unknown script"):
        app.post(
            "/api/scripts/run",
            json={"script_id": "nonexistent", "session_id": sample_session},
        )


def test_run_batch_async(app, sample_session, db):
    from open_uplift.keystore import store_api_key
    store_api_key(db, "anthropic", "default", "dummy-key")

    resp = app.post(
        "/api/scripts/run-batch",
        json={
            "scripts": ["transcript-compact"],
            "session_ids": [sample_session],
        },
    )
    assert resp.status_code == 202
    data = resp.get_json()
    assert "job_id" in data


def test_run_batch_missing_fields(app):
    resp = app.post("/api/scripts/run-batch", json={})
    assert resp.status_code == 400


def test_run_unprocessed_no_sessions(app, db):
    from open_uplift.keystore import store_api_key
    store_api_key(db, "anthropic", "default", "dummy-key")

    resp = app.post("/api/scripts/run-unprocessed")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["session_count"] == 0


def test_get_script_results(app, sample_session):
    resp = app.get(f"/api/scripts/results/{sample_session}")
    assert resp.status_code == 200
    assert resp.get_json() == []
