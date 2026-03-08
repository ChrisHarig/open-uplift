"""Integration tests for job queue API endpoints."""

import json

import pytest


def test_list_jobs_empty(app):
    resp = app.get("/api/jobs")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_get_job_not_found(app):
    resp = app.get("/api/jobs/nonexistent-id")
    assert resp.status_code == 404


def test_cancel_job(app, db):
    from open_uplift.job_queue import enqueue_job
    job_id = enqueue_job(db, "script-batch", {"scripts": [], "session_ids": []})
    db.commit()

    resp = app.post(f"/api/jobs/{job_id}/cancel")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "cancelled"


def test_cancel_completed_job(app, db):
    from open_uplift.job_queue import enqueue_job
    job_id = enqueue_job(db, "script-batch", {"scripts": [], "session_ids": []})
    db.execute("UPDATE jobs SET status = 'completed' WHERE id = ?", (job_id,))
    db.commit()

    resp = app.post(f"/api/jobs/{job_id}/cancel")
    assert resp.status_code == 404


def test_list_jobs_by_status(app, db):
    from open_uplift.job_queue import enqueue_job
    enqueue_job(db, "batch", {"scripts": [], "session_ids": []})
    db.commit()

    resp = app.get("/api/jobs?status=pending")
    assert len(resp.get_json()) == 1

    resp = app.get("/api/jobs?status=completed")
    assert len(resp.get_json()) == 0


def test_get_job_detail(app, db):
    from open_uplift.job_queue import enqueue_job
    job_id = enqueue_job(db, "script-batch", {"scripts": ["compact"], "session_ids": ["s1"]})
    db.commit()

    resp = app.get(f"/api/jobs/{job_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["id"] == job_id
    assert data["status"] == "pending"
