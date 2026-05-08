"""Integration tests for configuration API endpoints."""

import json
from unittest.mock import patch

import pytest


def test_get_run_mode_config(app):
    resp = app.get("/api/config/run-modes")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "enabled" in data
    assert "start_hour" in data
    assert "frequency_hours" in data


def test_put_run_mode_config(app):
    resp = app.put(
        "/api/config/run-modes",
        json={
            "enabled": True,
            "start_hour": 3,
            "frequency_hours": 12.0,
        },
    )
    assert resp.status_code == 200

    resp = app.get("/api/config/run-modes")
    data = resp.get_json()
    assert data["enabled"] is True
    assert data["start_hour"] == 3
    assert data["frequency_hours"] == 12.0


def test_get_api_keys_empty(app):
    resp = app.get("/api/api-keys")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_add_api_key(app):
    resp = app.post(
        "/api/api-keys",
        json={"provider": "anthropic", "key_name": "test", "api_key": "sk-test-123"},
    )
    assert resp.status_code == 201

    resp = app.get("/api/api-keys")
    keys = resp.get_json()
    assert len(keys) == 1
    assert keys[0]["provider"] == "anthropic"


def test_delete_api_key(app):
    app.post(
        "/api/api-keys",
        json={"provider": "anthropic", "key_name": "test", "api_key": "sk-test-123"},
    )
    resp = app.delete("/api/api-keys/anthropic/test")
    assert resp.status_code == 200

    resp = app.get("/api/api-keys")
    assert len(resp.get_json()) == 0


def test_get_scaffolds_empty(app):
    resp = app.get("/api/scaffolds")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_create_scaffold(app):
    resp = app.post(
        "/api/scaffolds",
        json={"display_name": "My Tool", "description": "A custom scaffold"},
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert "scaffold_id" in data
    assert "api_token" in data


def test_delete_scaffold(app):
    resp = app.post(
        "/api/scaffolds",
        json={"display_name": "Delete Me"},
    )
    scaffold_id = resp.get_json()["scaffold_id"]

    resp = app.delete(f"/api/scaffolds/{scaffold_id}")
    assert resp.status_code == 200


def test_get_script_config(app):
    """Test the new nested script-config endpoint."""
    resp = app.get("/api/script-config")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "compaction" in data
    assert "judge" in data
    assert "provider" in data["compaction"]
    assert "model" in data["judge"]


def test_put_script_config(app):
    """Test updating script config via new endpoint."""
    resp = app.put(
        "/api/script-config",
        json={
            "compaction": {
                "provider": "openai",
                "model": "gpt-4o-mini",
                "prompt_id": "compaction-default",
            },
            "judge": {
                "provider": "openai",
                "model": "gpt-4o",
                "prompt_id": "judge-default",
            },
        },
    )
    assert resp.status_code == 200

    resp = app.get("/api/script-config")
    data = resp.get_json()
    assert data["compaction"]["provider"] == "openai"
    assert data["judge"]["model"] == "gpt-4o"


# ---- Transcript endpoint ----

class TestTranscriptEndpoint:
    def test_get_transcript(self, app, db, sample_session, tmp_path, monkeypatch):
        """GET /api/sessions/<id>/transcript returns transcript data."""
        # Create a fake transcript file and register it in ingest_log
        transcript_file = tmp_path / f"{sample_session}.jsonl"
        transcript_data = [
            {"type": "conversation_start", "timestamp": "2026-02-20T10:00:00Z"},
            {"type": "message", "role": "user", "content": [{"type": "text", "text": "hello"}]},
            {"type": "message", "role": "assistant", "content": [{"type": "text", "text": "hi"}]},
        ]
        with open(transcript_file, "w") as f:
            for line in transcript_data:
                f.write(json.dumps(line) + "\n")

        db.execute(
            "INSERT INTO ingest_log (file_path, byte_offset, last_synced) VALUES (?, 0, '2026-02-20')",
            (str(transcript_file),),
        )
        db.commit()

        resp = app.get(f"/api/sessions/{sample_session}/transcript")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "transcript" in data

    def test_transcript_session_not_found(self, app):
        """GET /api/sessions/<id>/transcript returns 404 for unknown session."""
        resp = app.get("/api/sessions/nonexistent-id/transcript")
        assert resp.status_code == 404

    def test_transcript_file_not_found(self, app, db, sample_session):
        """GET /api/sessions/<id>/transcript returns 404 when file is missing."""
        db.execute(
            "INSERT INTO ingest_log (file_path, byte_offset, last_synced) VALUES (?, 0, '2026-02-20')",
            (f"/nonexistent/path/{sample_session}.jsonl",),
        )
        db.commit()

        resp = app.get(f"/api/sessions/{sample_session}/transcript")
        assert resp.status_code == 404
        assert "file not found" in resp.get_json()["error"].lower()


# ---- Time measurement endpoint ----

class TestTimeMeasurement:
    def test_get_session_time(self, app, db, sample_session):
        """GET /api/sessions/<id>/time returns time data."""
        resp = app.get(f"/api/sessions/{sample_session}/time")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "time" in data
        assert "concurrency" in data
        assert "active_minutes" in data["time"]
        assert "concurrent_sessions" in data["concurrency"]

    def test_session_time_not_found(self, app):
        """GET /api/sessions/<id>/time for nonexistent session returns zeroes."""
        resp = app.get("/api/sessions/nonexistent/time")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["time"]["active_minutes"] == 0
        assert data["concurrency"]["concurrent_sessions"] == 0
