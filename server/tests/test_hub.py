"""Tests for hub server endpoints."""

import json

import pytest

from tests.conftest import setup_hub_org


class TestHubJoin:
    def test_join_valid_invite(self, hub_app, db):
        org_id, admin_key, invite_code = setup_hub_org(db)

        resp = hub_app.post("/hub/join", json={
            "invite_code": invite_code,
            "member_name": "alice",
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["org_id"] == org_id
        assert data["org_name"] == "Test Org"
        assert "api_key" in data
        assert data["role"] == "member"
        assert "sharing_config" in data

    def test_join_invalid_invite(self, hub_app, db):
        setup_hub_org(db)

        resp = hub_app.post("/hub/join", json={
            "invite_code": "bad-code",
            "member_name": "bob",
        })
        assert resp.status_code == 403

    def test_join_duplicate_member(self, hub_app, db):
        org_id, admin_key, invite_code = setup_hub_org(db)

        # First join
        hub_app.post("/hub/join", json={
            "invite_code": invite_code,
            "member_name": "alice",
        })

        # Duplicate
        resp = hub_app.post("/hub/join", json={
            "invite_code": invite_code,
            "member_name": "alice",
        })
        assert resp.status_code == 409

    def test_join_missing_fields(self, hub_app, db):
        setup_hub_org(db)

        resp = hub_app.post("/hub/join", json={"invite_code": ""})
        assert resp.status_code == 400

    def test_join_revoked_invite(self, hub_app, db):
        org_id, admin_key, invite_code = setup_hub_org(db)

        # Revoke
        hub_app.post("/hub/invite/revoke",
            json={"invite_code": invite_code},
            headers={"Authorization": f"Bearer {admin_key}"},
        )

        resp = hub_app.post("/hub/join", json={
            "invite_code": invite_code,
            "member_name": "bob",
        })
        assert resp.status_code == 403


class TestHubPush:
    def test_push_aggregate(self, hub_app, db):
        org_id, admin_key, invite_code = setup_hub_org(db)

        resp = hub_app.post("/hub/push",
            json={
                "aggregate": {"total_sessions": 10, "total_tokens": 5000},
                "sessions": [],
            },
            headers={"Authorization": f"Bearer {admin_key}"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"

        # Verify stored
        row = db.execute("SELECT * FROM hub_aggregates WHERE org_id = ?", (org_id,)).fetchone()
        assert row is not None
        agg = json.loads(row["aggregate_data"])
        assert agg["total_sessions"] == 10

    def test_push_sessions(self, hub_app, db):
        org_id, admin_key, invite_code = setup_hub_org(db)

        resp = hub_app.post("/hub/push",
            json={
                "aggregate": {},
                "sessions": [
                    {"session_id": "s1", "started_at": "2026-01-01T00:00:00Z", "total_tokens": 100},
                    {"session_id": "s2", "started_at": "2026-01-02T00:00:00Z", "total_tokens": 200},
                ],
            },
            headers={"Authorization": f"Bearer {admin_key}"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["stored_sessions"] == 2

        rows = db.execute("SELECT * FROM hub_sessions WHERE org_id = ?", (org_id,)).fetchall()
        assert len(rows) == 2

    def test_push_unauthorized(self, hub_app, db):
        setup_hub_org(db)

        resp = hub_app.post("/hub/push",
            json={"aggregate": {}, "sessions": []},
            headers={"Authorization": "Bearer bad-key"},
        )
        assert resp.status_code == 401

    def test_push_no_auth(self, hub_app, db):
        resp = hub_app.post("/hub/push", json={"aggregate": {}, "sessions": []})
        assert resp.status_code == 401

    def test_push_sharing_config_enforcement(self, hub_app, db):
        """Sessions should be filtered by the org's sharing_config on the server side."""
        org_id, admin_key, invite_code = setup_hub_org(db)

        # Update org sharing_config to disable cost
        sharing = {"level": 2, "stats": {"tokens": True, "cost": False, "messages": False, "tool_calls": False, "uplift": False}}
        db.execute("UPDATE organizations SET sharing_config = ? WHERE org_id = ?", (json.dumps(sharing), org_id))
        db.commit()

        resp = hub_app.post("/hub/push",
            json={
                "aggregate": {},
                "sessions": [
                    {"session_id": "s1", "started_at": "2026-01-01T00:00:00Z", "total_cost_usd": 99.99, "total_input_tokens": 100},
                ],
            },
            headers={"Authorization": f"Bearer {admin_key}"},
        )
        assert resp.status_code == 200

        row = db.execute("SELECT session_data FROM hub_sessions WHERE org_id = ? AND session_id = 'org:s1'", (org_id,)).fetchone()
        # Session is stored but the server filters — verify the stored data
        row = db.execute("SELECT session_data FROM hub_sessions WHERE org_id = ?", (org_id,)).fetchone()
        assert row is not None
        data = json.loads(row["session_data"])
        # cost should be filtered out since stats.cost=False
        assert "total_cost_usd" not in data


class TestHubPull:
    def _setup_two_members(self, hub_app, db):
        """Setup org with admin + alice, both having pushed data."""
        org_id, admin_key, invite_code = setup_hub_org(db)

        # Join alice
        resp = hub_app.post("/hub/join", json={
            "invite_code": invite_code,
            "member_name": "alice",
        })
        alice_key = resp.get_json()["api_key"]

        # Admin pushes
        hub_app.post("/hub/push",
            json={
                "aggregate": {"total_sessions": 5, "total_tokens": 1000},
                "sessions": [{"session_id": "admin-s1", "started_at": "2026-01-01T00:00:00Z"}],
            },
            headers={"Authorization": f"Bearer {admin_key}"},
        )

        # Alice pushes
        hub_app.post("/hub/push",
            json={
                "aggregate": {"total_sessions": 3, "total_tokens": 500},
                "sessions": [{"session_id": "alice-s1", "started_at": "2026-01-01T00:00:00Z"}],
            },
            headers={"Authorization": f"Bearer {alice_key}"},
        )

        return org_id, admin_key, alice_key

    def test_pull_other_members_data(self, hub_app, db):
        org_id, admin_key, alice_key = self._setup_two_members(hub_app, db)

        # Admin pulls — should get alice's data, not own
        resp = hub_app.get("/hub/pull",
            headers={"Authorization": f"Bearer {admin_key}"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["aggregate"]["total_sessions"] == 3  # only alice's
        assert len(data["sessions"]) == 1
        assert data["sessions"][0]["session_id"] == "alice-s1"

    def test_pull_excludes_own_data(self, hub_app, db):
        org_id, admin_key, alice_key = self._setup_two_members(hub_app, db)

        # Alice pulls — should get admin's data
        resp = hub_app.get("/hub/pull",
            headers={"Authorization": f"Bearer {alice_key}"},
        )
        data = resp.get_json()
        assert data["aggregate"]["total_sessions"] == 5  # only admin's
        assert data["sessions"][0]["session_id"] == "admin-s1"

    def test_pull_since_param(self, hub_app, db):
        org_id, admin_key, alice_key = self._setup_two_members(hub_app, db)

        # Pull with a future since — should get no sessions
        resp = hub_app.get("/hub/pull?since=2099-01-01T00:00:00Z",
            headers={"Authorization": f"Bearer {admin_key}"},
        )
        data = resp.get_json()
        assert len(data["sessions"]) == 0

    def test_pull_unauthorized(self, hub_app, db):
        resp = hub_app.get("/hub/pull",
            headers={"Authorization": "Bearer bad"},
        )
        assert resp.status_code == 401


class TestHubInvite:
    def test_admin_can_create_invite(self, hub_app, db):
        org_id, admin_key, _ = setup_hub_org(db)

        resp = hub_app.post("/hub/invite",
            headers={"Authorization": f"Bearer {admin_key}"},
        )
        assert resp.status_code == 201
        assert "invite_code" in resp.get_json()

    def test_member_cannot_create_invite(self, hub_app, db):
        org_id, admin_key, invite_code = setup_hub_org(db)

        # Join as member
        resp = hub_app.post("/hub/join", json={
            "invite_code": invite_code,
            "member_name": "alice",
        })
        alice_key = resp.get_json()["api_key"]

        # Try to create invite
        resp = hub_app.post("/hub/invite",
            headers={"Authorization": f"Bearer {alice_key}"},
        )
        assert resp.status_code == 403

    def test_admin_can_revoke_invite(self, hub_app, db):
        org_id, admin_key, invite_code = setup_hub_org(db)

        resp = hub_app.post("/hub/invite/revoke",
            json={"invite_code": invite_code},
            headers={"Authorization": f"Bearer {admin_key}"},
        )
        assert resp.status_code == 200

        # Verify revoked
        row = db.execute("SELECT revoked_at FROM hub_invites WHERE invite_code = ?", (invite_code,)).fetchone()
        assert row["revoked_at"] is not None

    def test_member_cannot_revoke_invite(self, hub_app, db):
        org_id, admin_key, invite_code = setup_hub_org(db)

        resp = hub_app.post("/hub/join", json={
            "invite_code": invite_code,
            "member_name": "alice",
        })
        alice_key = resp.get_json()["api_key"]

        resp = hub_app.post("/hub/invite/revoke",
            json={"invite_code": invite_code},
            headers={"Authorization": f"Bearer {alice_key}"},
        )
        assert resp.status_code == 403


class TestHubConfig:
    def test_get_config(self, hub_app, db):
        org_id, admin_key, _ = setup_hub_org(db)

        resp = hub_app.get("/hub/config",
            headers={"Authorization": f"Bearer {admin_key}"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["org_id"] == org_id
        assert "sharing_config" in data

    def test_admin_can_update_config(self, hub_app, db):
        org_id, admin_key, _ = setup_hub_org(db)

        new_config = {"level": 2, "stats": {"tokens": True, "cost": False}}
        resp = hub_app.put("/hub/config",
            json={"sharing_config": new_config},
            headers={"Authorization": f"Bearer {admin_key}"},
            content_type="application/json",
        )
        assert resp.status_code == 200

        # Verify
        row = db.execute("SELECT sharing_config FROM organizations WHERE org_id = ?", (org_id,)).fetchone()
        assert json.loads(row["sharing_config"]) == new_config

    def test_member_cannot_update_config(self, hub_app, db):
        org_id, admin_key, invite_code = setup_hub_org(db)

        resp = hub_app.post("/hub/join", json={
            "invite_code": invite_code,
            "member_name": "alice",
        })
        alice_key = resp.get_json()["api_key"]

        resp = hub_app.put("/hub/config",
            json={"sharing_config": {"level": 2}},
            headers={"Authorization": f"Bearer {alice_key}"},
            content_type="application/json",
        )
        assert resp.status_code == 403


class TestHubMembers:
    def test_list_members(self, hub_app, db):
        org_id, admin_key, invite_code = setup_hub_org(db)

        hub_app.post("/hub/join", json={
            "invite_code": invite_code,
            "member_name": "alice",
        })

        resp = hub_app.get("/hub/members",
            headers={"Authorization": f"Bearer {admin_key}"},
        )
        assert resp.status_code == 200
        members = resp.get_json()
        assert len(members) == 2
        names = {m["member_name"] for m in members}
        assert names == {"admin", "alice"}
