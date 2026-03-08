"""Integration tests for sync API endpoints."""

import pytest
from unittest.mock import patch


def test_sync_endpoint(app, monkeypatch):
    monkeypatch.setattr(
        "open_uplift.api.sync_all",
        lambda: {"sessions_new": 0, "sessions_updated": 0, "messages_added": 0},
    )
    resp = app.post("/api/sync")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "sessions_new" in data


def test_sync_status(app):
    resp = app.get("/api/sync/status")
    assert resp.status_code == 200
    data = resp.get_json()
    # Should return last sync info (might be empty initially)
    assert isinstance(data, dict)
