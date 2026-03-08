"""Tests for uplift analytics API endpoints."""

import pytest


class TestUpliftDistribution:
    def test_distribution_with_data(self, app, db, sample_uplift_data):
        resp = app.get("/api/uplift/distribution?output_id=llm-judge")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "buckets" in data
        assert "values" in data
        assert "stats" in data
        assert len(data["values"]) == 2  # Two sessions with llm-judge outputs
        assert data["stats"]["count"] == 2

    def test_distribution_empty(self, app):
        resp = app.get("/api/uplift/distribution?output_id=nonexistent")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["buckets"] == []
        assert data["values"] == []
        assert data["stats"] == {}

    def test_distribution_single_value(self, app, db, sample_session_with_results):
        """When only one uplift output exists, it should still work."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        resp_row = db.execute(
            "SELECT id FROM survey_responses WHERE session_id = ?",
            (sample_session_with_results,),
        ).fetchone()
        db.execute(
            """INSERT OR IGNORE INTO uplift_outputs
               (session_id, survey_response_id, output_id, uplift_factor, metadata, timestamp)
               VALUES (?, ?, 'single-test', 3.0, '{}', ?)""",
            (sample_session_with_results, resp_row["id"], now),
        )
        db.commit()

        resp = app.get("/api/uplift/distribution?output_id=single-test")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["values"]) == 1
        assert data["stats"]["count"] == 1


class TestUpliftTimeseries:
    def test_timeseries_with_data(self, app, db, sample_uplift_data):
        resp = app.get("/api/uplift/timeseries?output_id=llm-judge")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert "day" in data[0]
        assert "avg_uplift" in data[0]
        assert "count" in data[0]

    def test_timeseries_custom_days(self, app, db, sample_uplift_data):
        resp = app.get("/api/uplift/timeseries?output_id=llm-judge&days=7")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)


class TestUpliftByProject:
    def test_by_project(self, app, db, sample_uplift_data):
        resp = app.get("/api/uplift/by-project?output_id=llm-judge")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["project_name"] == "myproject"
        assert data[0]["count"] >= 1


class TestUpliftByScaffold:
    def test_by_scaffold(self, app, db, sample_uplift_data):
        resp = app.get("/api/uplift/by-scaffold?output_id=llm-judge")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["scaffold"] == "claude_code"


class TestUpliftByModel:
    def test_by_model(self, app, db, sample_uplift_data):
        resp = app.get("/api/uplift/by-model?output_id=llm-judge")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["model"] == "claude-sonnet-4-6"


class TestUpliftAgreement:
    def test_agreement_with_both_outputs(self, app, db, sample_uplift_data):
        """Sessions with both human-est and llm-judge should appear."""
        resp = app.get("/api/uplift/agreement")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1
        entry = data[0]
        assert "session_id" in entry
        assert "human" in entry
        assert "llm" in entry
        assert entry["human"] is not None
        assert entry["llm"] is not None

    def test_agreement_empty(self, app):
        resp = app.get("/api/uplift/agreement")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data == []


class TestUpliftConcurrency:
    def test_concurrency_with_data(self, app, db, sample_uplift_data):
        resp = app.get("/api/uplift/concurrency?output_id=llm-judge")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1
        entry = data[0]
        assert "session_id" in entry
        assert "uplift_factor" in entry
        assert "concurrent_sessions" in entry
        assert "adjusted_minutes" in entry

    def test_concurrency_accepts_output_id(self, app, db, sample_uplift_data):
        resp = app.get("/api/uplift/concurrency?output_id=human-est")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
