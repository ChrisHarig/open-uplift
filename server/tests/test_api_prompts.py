"""Tests for prompt API endpoints."""

import json

import pytest


class TestPromptsList:
    def test_list_prompts(self, app):
        resp = app.get("/api/prompts")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        # Default prompts should be seeded
        ids = [p["prompt_id"] for p in data]
        assert "compaction-default" in ids
        assert "judge-default" in ids

    def test_filter_by_category(self, app):
        resp = app.get("/api/prompts?category=compaction")
        assert resp.status_code == 200
        data = resp.get_json()
        assert all(p["category"] == "compaction" for p in data)
        assert len(data) >= 1


class TestPromptsCreate:
    def test_create_prompt(self, app):
        resp = app.post("/api/prompts", json={
            "prompt_id": "test-custom",
            "category": "judge",
            "name": "My Custom Prompt",
            "system_prompt": "You are a custom judge.",
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["prompt_id"] == "test-custom"

        # Verify it appears in list
        resp = app.get("/api/prompts")
        ids = [p["prompt_id"] for p in resp.get_json()]
        assert "test-custom" in ids

    def test_create_prompt_missing_field(self, app):
        resp = app.post("/api/prompts", json={
            "prompt_id": "incomplete",
            "category": "judge",
            # Missing name and system_prompt
        })
        assert resp.status_code == 400

    def test_create_duplicate_prompt_id(self, app):
        app.post("/api/prompts", json={
            "prompt_id": "dup-test",
            "category": "judge",
            "name": "First",
            "system_prompt": "prompt 1",
        })
        resp = app.post("/api/prompts", json={
            "prompt_id": "dup-test",
            "category": "judge",
            "name": "Second",
            "system_prompt": "prompt 2",
        })
        assert resp.status_code == 409

    def test_create_prompt_with_output_schema(self, app):
        schema = [{"name": "score", "type": "numeric", "required": True}]
        resp = app.post("/api/prompts", json={
            "prompt_id": "schema-test",
            "category": "judge",
            "name": "Schema Prompt",
            "system_prompt": "Evaluate this.",
            "output_schema": schema,
        })
        assert resp.status_code == 201

        resp = app.get("/api/prompts?category=judge")
        prompt = next(p for p in resp.get_json() if p["prompt_id"] == "schema-test")
        assert prompt["output_schema"] == schema


class TestPromptsUpdate:
    def test_update_prompt(self, app, db, sample_prompt):
        resp = app.put(f"/api/prompts/{sample_prompt}", json={
            "name": "Renamed Prompt",
            "description": "New description",
        })
        assert resp.status_code == 200
        new_id = resp.get_json().get("new_prompt_id")

        # Update creates a new versioned prompt and archives the old one
        resp = app.get("/api/prompts")
        prompts = resp.get_json()
        # The new version should exist
        prompt = next(p for p in prompts if p["prompt_id"] == (new_id or sample_prompt))
        assert prompt["name"] == "Renamed Prompt"
        assert prompt["description"] == "New description"

    def test_update_prompt_not_found(self, app):
        resp = app.put("/api/prompts/nonexistent", json={"name": "x"})
        assert resp.status_code == 404


class TestPromptsDelete:
    def test_delete_custom_prompt(self, app, db, sample_prompt):
        resp = app.delete(f"/api/prompts/{sample_prompt}")
        assert resp.status_code == 200

        # Verify removal
        resp = app.get("/api/prompts")
        ids = [p["prompt_id"] for p in resp.get_json()]
        assert sample_prompt not in ids

    def test_delete_default_prompt_blocked(self, app):
        resp = app.delete("/api/prompts/compaction-default")
        assert resp.status_code == 400
        assert "default" in resp.get_json()["error"].lower()

    def test_delete_prompt_not_found(self, app):
        resp = app.delete("/api/prompts/nonexistent")
        assert resp.status_code == 404
