"""Tests for sync.py HTTP client functions with mocked requests."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from open_uplift.sync import (
    _gather_aggregate,
    _gather_sessions,
    join_org,
    pull_org,
    push_org,
    sync_org,
)


class TestGatherAggregate:
    def test_basic_aggregate(self, db, sample_session_with_results):
        sharing_config = {
            "level": 1,
            "stats": {"tokens": True, "cost": True, "messages": True, "tool_calls": True, "uplift": True},
        }
        # Ensure the judge result has session_message_count set
        db.execute(
            "UPDATE script_results SET session_message_count = 5 WHERE script_id = 'llm-time-estimate'"
        )
        db.commit()
        result = _gather_aggregate(db, sharing_config)
        assert result["total_sessions"] == 1
        assert result["total_tokens"] > 0
        assert "total_cost_usd" in result
        assert "total_messages" in result

    def test_aggregate_respects_config(self, db, sample_session_with_results):
        sharing_config = {
            "level": 1,
            "stats": {"tokens": True, "cost": False, "messages": False, "tool_calls": False, "uplift": False},
        }
        db.execute(
            "UPDATE script_results SET session_message_count = 5 WHERE script_id = 'llm-time-estimate'"
        )
        db.commit()
        result = _gather_aggregate(db, sharing_config)
        assert "total_sessions" in result
        assert "total_cost_usd" not in result
        assert "total_messages" not in result

    def test_unjudged_sessions_excluded(self, db, sample_session):
        """Sessions without judge results should not be counted."""
        sharing_config = {
            "level": 1,
            "stats": {"tokens": True, "cost": True, "messages": True, "tool_calls": True, "uplift": True},
        }
        result = _gather_aggregate(db, sharing_config)
        assert result["total_sessions"] == 0


class TestGatherSessions:
    def test_level1_returns_empty(self, db, sample_session):
        result = _gather_sessions(db, {"level": 1, "stats": {}}, None)
        assert result == []

    def test_level2_returns_judged_sessions(self, db, sample_session_with_results):
        sharing_config = {
            "level": 2,
            "stats": {"tokens": True, "cost": True, "messages": True, "tool_calls": True, "uplift": True},
        }
        db.execute(
            "UPDATE script_results SET session_message_count = 5 WHERE script_id = 'llm-time-estimate'"
        )
        db.commit()
        result = _gather_sessions(db, sharing_config, None)
        assert len(result) == 1
        assert result[0]["session_id"] == sample_session_with_results

    def test_level2_excludes_unjudged(self, db, sample_session):
        sharing_config = {
            "level": 2,
            "stats": {"tokens": True, "cost": True, "messages": True, "tool_calls": True, "uplift": True},
        }
        result = _gather_sessions(db, sharing_config, None)
        assert result == []


class TestJoinOrg:
    @patch("open_uplift.sync.requests.post")
    def test_join_success(self, mock_post, db):
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {
            "org_id": "test-org",
            "org_name": "Test Org",
            "api_key": "key-123",
            "sharing_config": {"level": 1, "stats": {"tokens": True}},
            "role": "member",
        }
        mock_resp.headers = {"content-type": "application/json"}
        mock_post.return_value = mock_resp

        result = join_org(db, "http://localhost:7070", "invite-abc", "alice")
        assert result["org_id"] == "test-org"
        assert result["org_name"] == "Test Org"

        # Verify stored in DB
        row = db.execute("SELECT * FROM org_memberships WHERE org_id = 'test-org'").fetchone()
        assert row is not None
        assert row["hub_url"] == "http://localhost:7070"
        assert row["api_key"] == "key-123"
        assert row["member_name"] == "alice"

    @patch("open_uplift.sync.requests.post")
    def test_join_failure(self, mock_post, db):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.json.return_value = {"error": "Invalid invite"}
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.text = "Invalid invite"
        mock_post.return_value = mock_resp

        with pytest.raises(RuntimeError, match="Join failed"):
            join_org(db, "http://localhost:7070", "bad-code", "alice")


class TestPushOrg:
    @patch("open_uplift.sync.requests.post")
    def test_push_success(self, mock_post, db, sample_session):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "ok", "stored_sessions": 0}
        mock_resp.headers = {"content-type": "application/json"}
        mock_post.return_value = mock_resp

        membership = {
            "org_id": "test-org",
            "hub_url": "http://localhost:7070",
            "api_key": "key-123",
            "sharing_config": json.dumps({"level": 1, "stats": {"tokens": True, "cost": True}}),
            "last_push_at": None,
        }

        # Insert membership so update works
        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            "INSERT INTO org_memberships (org_id, org_name, member_name, hub_url, api_key, sharing_config, joined_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("test-org", "Test", "me", "http://localhost:7070", "key-123", membership["sharing_config"], now),
        )
        db.commit()

        result = push_org(db, membership)
        assert result["status"] == "ok"

        # Verify last_push_at was updated
        row = db.execute("SELECT last_push_at FROM org_memberships WHERE org_id = 'test-org'").fetchone()
        assert row["last_push_at"] is not None

    @patch("open_uplift.sync.requests.post")
    def test_push_no_hub_url(self, mock_post, db):
        with pytest.raises(RuntimeError, match="No hub_url"):
            push_org(db, {"org_id": "x", "hub_url": None, "api_key": None})


class TestPullOrg:
    @patch("open_uplift.sync.requests.get")
    def test_pull_success(self, mock_get, db):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "org_name": "Test Org",
            "sharing_config": {"level": 1, "stats": {"tokens": True}},
            "aggregate": {"total_sessions": 5, "total_tokens": 1000, "member_count": 2},
            "sessions": [],
            "member_count": 2,
            "members": [{"member_name": "alice"}, {"member_name": "bob"}],
        }
        mock_resp.headers = {"content-type": "application/json"}
        mock_get.return_value = mock_resp

        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            "INSERT INTO org_memberships (org_id, org_name, member_name, hub_url, api_key, sharing_config, joined_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("test-org", "Test", "me", "http://localhost:7070", "key-123", "{}", now),
        )
        db.commit()

        membership = {
            "org_id": "test-org",
            "hub_url": "http://localhost:7070",
            "api_key": "key-123",
            "last_pull_at": None,
        }

        result = pull_org(db, membership)
        assert result["status"] == "ok"
        assert result["aggregate"]["total_sessions"] == 5


class TestSyncOrg:
    @patch("open_uplift.sync.requests.get")
    @patch("open_uplift.sync.requests.post")
    def test_sync_push_then_pull(self, mock_post, mock_get, db, sample_session):
        # Push mock
        push_resp = MagicMock()
        push_resp.status_code = 200
        push_resp.json.return_value = {"status": "ok", "stored_sessions": 0}
        push_resp.headers = {"content-type": "application/json"}
        mock_post.return_value = push_resp

        # Pull mock
        pull_resp = MagicMock()
        pull_resp.status_code = 200
        pull_resp.json.return_value = {
            "org_name": "Test",
            "sharing_config": {"level": 1},
            "aggregate": {"total_sessions": 3},
            "sessions": [],
            "member_count": 2,
            "members": [],
        }
        pull_resp.headers = {"content-type": "application/json"}
        mock_get.return_value = pull_resp

        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            "INSERT INTO org_memberships (org_id, org_name, member_name, hub_url, api_key, sharing_config, joined_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("test-org", "Test", "me", "http://localhost:7070", "key-123",
             json.dumps({"level": 1, "stats": {"tokens": True, "cost": True}}), now),
        )
        db.commit()

        membership = {
            "org_id": "test-org",
            "hub_url": "http://localhost:7070",
            "api_key": "key-123",
            "sharing_config": json.dumps({"level": 1, "stats": {"tokens": True, "cost": True}}),
            "last_push_at": None,
            "last_pull_at": None,
        }

        result = sync_org(db, membership)
        assert "push" in result
        assert "pull" in result
        assert result["push"]["status"] == "ok"
        assert result["pull"]["status"] == "ok"
