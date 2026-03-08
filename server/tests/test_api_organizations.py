"""Tests for organization API endpoints."""

import json

import pytest


class TestOrganizationsCRUD:
    def test_list_organizations(self, app):
        resp = app.get("/api/organizations")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) >= 0

    def test_create_organization(self, app):
        resp = app.post("/api/organizations", json={
            "name": "New Org",
            "description": "A brand new org",
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["org_id"] == "new-org"
        assert data["name"] == "New Org"

    def test_create_organization_missing_name(self, app):
        resp = app.post("/api/organizations", json={"description": "no name"})
        assert resp.status_code == 400

    def test_create_duplicate_organization(self, app):
        app.post("/api/organizations", json={"name": "Dupe Org"})
        resp = app.post("/api/organizations", json={"name": "Dupe Org"})
        assert resp.status_code == 409

    def test_get_organization_detail(self, app, db, sample_organization):
        resp = app.get(f"/api/organizations/{sample_organization}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["name"] == "Test Organization"
        assert "folders" in data
        assert len(data["folders"]) == 2
        assert "stats" in data

    def test_get_organization_not_found(self, app):
        resp = app.get("/api/organizations/nonexistent")
        assert resp.status_code == 404

    def test_update_organization(self, app, db, sample_organization):
        resp = app.put(f"/api/organizations/{sample_organization}", json={
            "name": "Updated Name",
            "description": "Updated desc",
        })
        assert resp.status_code == 200

        resp = app.get(f"/api/organizations/{sample_organization}")
        data = resp.get_json()
        assert data["name"] == "Updated Name"
        assert data["description"] == "Updated desc"

    def test_update_organization_not_found(self, app):
        resp = app.put("/api/organizations/nonexistent", json={"name": "x"})
        assert resp.status_code == 404

    def test_delete_organization(self, app, db, sample_organization):
        resp = app.delete(f"/api/organizations/{sample_organization}")
        assert resp.status_code == 200

        resp = app.get(f"/api/organizations/{sample_organization}")
        assert resp.status_code == 404

    def test_delete_organization_not_found(self, app):
        resp = app.delete("/api/organizations/nonexistent")
        assert resp.status_code == 404


class TestOrganizationFolders:
    def test_add_folders(self, app, db, sample_organization):
        resp = app.post(f"/api/organizations/{sample_organization}/folders", json={
            "folder_paths": ["/Users/dev/new-project"],
        })
        assert resp.status_code == 200

        resp = app.get(f"/api/organizations/{sample_organization}")
        folders = resp.get_json()["folders"]
        paths = [f["folder_path"] for f in folders]
        assert "/Users/dev/new-project" in paths

    def test_remove_folders(self, app, db, sample_organization):
        resp = app.post(f"/api/organizations/{sample_organization}/remove-folders", json={
            "folder_paths": ["/Users/dev/other-project"],
        })
        assert resp.status_code == 200

        resp = app.get(f"/api/organizations/{sample_organization}")
        folders = resp.get_json()["folders"]
        paths = [f["folder_path"] for f in folders]
        assert "/Users/dev/other-project" not in paths

    def test_folder_conflict_detection(self, app, db, sample_organization):
        """Adding a child path of an existing org folder to a different org should conflict."""
        # Create a second org
        app.post("/api/organizations", json={"name": "Other Org"})
        # Try to add a child of test-org's folder to other-org
        resp = app.post("/api/organizations/other-org/folders", json={
            "folder_paths": ["/Users/dev/myproject/subdir"],
        })
        assert resp.status_code == 409
        assert "conflicts" in resp.get_json()["error"].lower()

    def test_unassigned_folders(self, app, db, sample_session):
        """Sessions with paths not in any org should show up as unassigned."""
        resp = app.get("/api/organizations/unassigned-folders")
        assert resp.status_code == 200
        data = resp.get_json()
        # The sample session path should be unassigned (no org claimed it yet)
        paths = [f["project_path"] for f in data]
        assert "/Users/dev/myproject" in paths

    def test_dismiss_folder(self, app, db, sample_session):
        resp = app.post("/api/organizations/dismiss-folder", json={
            "folder_path": "/Users/dev/myproject",
        })
        assert resp.status_code == 200

        # After dismissing, should no longer appear in unassigned
        resp = app.get("/api/organizations/unassigned-folders")
        paths = [f["project_path"] for f in resp.get_json()]
        assert "/Users/dev/myproject" not in paths


class TestOrganizationAnalytics:
    def test_analytics_returns_data(self, app, db, sample_organization, sample_uplift_data):
        resp = app.get(f"/api/organizations/{sample_organization}/analytics")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "totals" in data
        assert "uplift" in data
        assert "daily" in data
        assert "uplift_timeseries" in data
        assert data["totals"]["total_sessions"] >= 1

    def test_analytics_not_found(self, app):
        resp = app.get("/api/organizations/nonexistent/analytics")
        assert resp.status_code == 404

    def test_org_stats_aggregate_across_folders(self, app, db, sample_organization):
        """Stats should include sessions from all org folders."""
        resp = app.get(f"/api/organizations/{sample_organization}")
        data = resp.get_json()
        assert data["stats"]["total_sessions"] >= 1

    def test_create_org_with_folders(self, app):
        resp = app.post("/api/organizations", json={
            "name": "Org With Folders",
            "folder_paths": ["/some/path", "/another/path"],
        })
        assert resp.status_code == 201
        org_id = resp.get_json()["org_id"]

        resp = app.get(f"/api/organizations/{org_id}")
        assert len(resp.get_json()["folders"]) == 2
