"""Tests for the evaluator system."""

import json
from pathlib import Path
import pytest

from open_uplift.evaluators.base import Evaluator, EvaluatorResult
from open_uplift.evaluators.registry import EvaluatorRegistry


FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# EvaluatorResult tests
# ---------------------------------------------------------------------------


class TestEvaluatorResult:
    def test_success(self):
        r = EvaluatorResult(evaluator_id="test", value=42, value_type="numeric")
        assert r.success is True
        assert r.error is None

    def test_error(self):
        r = EvaluatorResult(evaluator_id="test", value=None, value_type="numeric", error="boom")
        assert r.success is False
        assert r.error == "boom"

    def test_metadata_default(self):
        r = EvaluatorResult(evaluator_id="test", value=True, value_type="boolean")
        assert r.metadata == {}


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


class _DummyEvaluator(Evaluator):
    evaluator_id = "dummy"
    name = "Dummy"
    category = "test"
    description = "A dummy evaluator for testing"

    def run(self, db, session_id):
        return EvaluatorResult(evaluator_id=self.evaluator_id, value="ok", value_type="string")


class TestRegistry:
    def test_register_and_get(self):
        reg = EvaluatorRegistry()
        e = _DummyEvaluator()
        reg.register(e)
        assert reg.get("dummy") is e
        assert reg.has("dummy")
        assert not reg.has("nonexistent")

    def test_list(self):
        reg = EvaluatorRegistry()
        reg.register(_DummyEvaluator())
        assert len(reg.list()) == 1
        assert reg.list()[0].evaluator_id == "dummy"

    def test_list_available(self):
        reg = EvaluatorRegistry()
        reg.register(_DummyEvaluator())
        available = reg.list_available()
        assert len(available) == 1
        assert available[0]["evaluator_id"] == "dummy"
        assert available[0]["category"] == "test"

    def test_run(self):
        reg = EvaluatorRegistry()
        reg.register(_DummyEvaluator())
        result = reg.run(None, "dummy", "session-1")
        assert result.value == "ok"

    def test_run_unknown(self):
        reg = EvaluatorRegistry()
        with pytest.raises(ValueError, match="Unknown evaluator"):
            reg.run(None, "nonexistent", "session-1")


# ---------------------------------------------------------------------------
# Built-in evaluator integration tests
# ---------------------------------------------------------------------------


class TestBuiltinEvaluatorsRegistered:
    """Verify that the global registry contains the built-in evaluators."""

    def test_builtins_present(self):
        from open_uplift.evaluators.registry import get_registry

        # Force re-init for a clean state
        from open_uplift.evaluators import registry as reg_mod
        reg_mod._registry = EvaluatorRegistry()

        registry = get_registry()
        assert registry.has("transcript-compact")
        assert registry.has("llm-time-estimate")
        assert registry.has("time-with-ai")

    def test_evaluator_metadata(self):
        from open_uplift.evaluators.registry import get_registry

        from open_uplift.evaluators import registry as reg_mod
        reg_mod._registry = EvaluatorRegistry()

        registry = get_registry()
        judge = registry.get("llm-time-estimate")
        assert judge is not None
        d = judge.to_dict()
        assert d["category"] == "builtin"
        assert d["requires_llm"] is True
        assert "transcript-compact" in d["depends_on"]


# ---------------------------------------------------------------------------
# CompactionEvaluator unit test
# ---------------------------------------------------------------------------


class TestCompactionEvaluator:
    def test_no_transcript(self, db, sample_session):
        from open_uplift.evaluators.compaction import CompactionEvaluator

        e = CompactionEvaluator()
        result = e.run(db, sample_session)
        assert not result.success
        assert "not found" in result.error

    def test_success(self, db, sample_session, mock_llm, monkeypatch, tmp_path):
        from open_uplift.evaluators.compaction import CompactionEvaluator

        monkeypatch.setattr("open_uplift.scripts.get_api_key", lambda db, provider, name="default": "fake-key")

        transcript_path = tmp_path / f"{sample_session}.jsonl"
        entry = {
            "type": "conversation",
            "message": {"role": "user", "content": "Hello"},
            "timestamp": "2026-02-20T10:00:00Z",
        }
        transcript_path.write_text(json.dumps(entry) + "\n")
        db.execute(
            "INSERT INTO ingest_log (file_path, byte_offset, last_synced) VALUES (?, 0, '2026-02-20T10:00:00Z')",
            (str(transcript_path),),
        )
        db.commit()

        e = CompactionEvaluator()
        result = e.run(db, sample_session)
        assert result.success
        assert result.value_type == "string"
        assert result.metadata.get("compacted_transcript")


# ---------------------------------------------------------------------------
# JudgeEvaluator unit test
# ---------------------------------------------------------------------------


class TestJudgeEvaluator:
    def test_with_compacted_transcript(self, db, sample_session, mock_llm, monkeypatch):
        from open_uplift.evaluators.judge import JudgeEvaluator

        monkeypatch.setattr("open_uplift.scripts.get_api_key", lambda db, provider, name="default": "fake-key")

        # Insert compaction result
        db.execute(
            """INSERT INTO script_results
               (session_id, script_id, status, result, started_at, completed_at)
               VALUES (?, 'transcript-compact', 'completed', ?, '2026-01-01', '2026-01-01')""",
            (sample_session, json.dumps({"compacted_transcript": "Session summary here"})),
        )
        db.commit()

        e = JudgeEvaluator()
        result = e.run(db, sample_session)
        assert result.success
        assert result.value == 30
        assert result.value_type == "numeric"
        assert result.confidence == "medium"


# ---------------------------------------------------------------------------
# TimeWithAIEvaluator unit test
# ---------------------------------------------------------------------------


class TestTimeWithAIEvaluator:
    def test_basic(self, db, sample_session):
        from open_uplift.evaluators.time_with_ai import TimeWithAIEvaluator

        e = TimeWithAIEvaluator()
        result = e.run(db, sample_session)
        assert result.success
        assert result.value_type == "numeric"
        assert isinstance(result.value, (int, float))
        assert result.metadata.get("active_windows") is not None


# ---------------------------------------------------------------------------
# run_script backward compatibility
# ---------------------------------------------------------------------------


class TestRunScriptBackwardCompat:
    def test_dispatches_to_evaluator(self, db, sample_session, mock_llm, monkeypatch, tmp_path):
        from open_uplift.scripts import run_script

        monkeypatch.setattr("open_uplift.scripts.get_api_key", lambda db, provider, name="default": "fake-key")

        transcript_path = tmp_path / f"{sample_session}.jsonl"
        entry = {
            "type": "conversation",
            "message": {"role": "user", "content": "Hello"},
            "timestamp": "2026-02-20T10:00:00Z",
        }
        transcript_path.write_text(json.dumps(entry) + "\n")
        db.execute(
            "INSERT INTO ingest_log (file_path, byte_offset, last_synced) VALUES (?, 0, '2026-02-20T10:00:00Z')",
            (str(transcript_path),),
        )
        db.commit()

        result = run_script(db, "transcript-compact", sample_session)
        assert "error" not in result
        assert "compacted_transcript" in result

    def test_unknown_script(self, db, sample_session):
        from open_uplift.scripts import run_script

        with pytest.raises(ValueError, match="Unknown"):
            run_script(db, "nonexistent", sample_session)

    def test_time_with_ai(self, db, sample_session):
        """time-with-ai is a new evaluator accessible via run_script."""
        from open_uplift.scripts import run_script

        result = run_script(db, "time-with-ai", sample_session)
        assert "error" not in result
        assert "active_minutes" in result


