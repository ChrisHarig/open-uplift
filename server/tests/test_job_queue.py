"""Tests for the async job queue."""

import json
import threading
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from open_uplift.job_queue import (
    JobWorker,
    _default_run_mode_config,
    _get_run_mode_config,
    _run_batch_job,
    _set_run_mode_config,
    cancel_job,
    enqueue_job,
    get_job,
    list_jobs,
    _find_unprocessed_session_ids,
)


def test_enqueue_job(db):
    job_id = enqueue_job(db, "script-batch", {"scripts": ["transcript-compact"], "session_ids": ["s1"]})
    db.commit()

    assert job_id
    assert len(job_id) == 36  # UUID format


def test_get_job(db):
    job_id = enqueue_job(db, "script-batch", {"scripts": ["transcript-compact"], "session_ids": ["s1"]})
    db.commit()

    job = get_job(db, job_id)
    assert job is not None
    assert job["id"] == job_id
    assert job["status"] == "pending"
    assert job["job_type"] == "script-batch"
    assert job["payload"]["scripts"] == ["transcript-compact"]


def test_get_job_not_found(db):
    job = get_job(db, "nonexistent-id")
    assert job is None


def test_list_jobs(db):
    enqueue_job(db, "script-batch", {"scripts": [], "session_ids": []})
    enqueue_job(db, "daily-batch", {"scripts": [], "session_ids": []})
    db.commit()

    jobs = list_jobs(db)
    assert len(jobs) == 2


def test_list_jobs_by_status(db):
    job_id = enqueue_job(db, "script-batch", {"scripts": [], "session_ids": []})
    db.commit()

    pending = list_jobs(db, status="pending")
    assert len(pending) == 1

    completed = list_jobs(db, status="completed")
    assert len(completed) == 0


def test_cancel_job(db):
    job_id = enqueue_job(db, "script-batch", {"scripts": [], "session_ids": []})
    db.commit()

    result = cancel_job(db, job_id)
    assert result is True

    job = get_job(db, job_id)
    assert job["status"] == "cancelled"


def test_cancel_completed_job(db):
    job_id = enqueue_job(db, "script-batch", {"scripts": [], "session_ids": []})
    db.execute("UPDATE jobs SET status = 'completed' WHERE id = ?", (job_id,))
    db.commit()

    result = cancel_job(db, job_id)
    assert result is False


def test_cancel_nonexistent_job(db):
    result = cancel_job(db, "nonexistent")
    assert result is False


def test_find_unprocessed_session_ids(db, sample_session):
    """All sessions missing script results should be found by default."""
    unprocessed = _find_unprocessed_session_ids(db)
    assert sample_session in unprocessed


def test_find_unprocessed_session_ids_require_survey(db, sample_session):
    """With require_survey=True, only sessions with survey responses are found."""
    # Without survey, should NOT be found
    unprocessed = _find_unprocessed_session_ids(db, require_survey=True)
    assert sample_session not in unprocessed

    # After adding survey response, should be found
    from open_uplift.surveys import submit_survey_response
    submit_survey_response(db, sample_session, "survey-1", answers={"human-est": 3.0})
    db.commit()

    unprocessed = _find_unprocessed_session_ids(db, require_survey=True)
    assert sample_session in unprocessed


def test_find_unprocessed_session_ids_none_missing(db, sample_session):
    """Sessions with completed script results should not appear."""
    # Insert completed script results for both scripts
    for script_id in ["transcript-compact", "llm-time-estimate"]:
        db.execute(
            """INSERT INTO script_results
               (session_id, script_id, status, started_at, completed_at)
               VALUES (?, ?, 'completed', '2026-01-01', '2026-01-01')""",
            (sample_session, script_id),
        )
    db.commit()

    unprocessed = _find_unprocessed_session_ids(db)
    assert sample_session not in unprocessed


def test_list_jobs_with_multiple_statuses(db):
    j1 = enqueue_job(db, "batch", {"scripts": [], "session_ids": []})
    j2 = enqueue_job(db, "batch", {"scripts": [], "session_ids": []})
    db.execute("UPDATE jobs SET status = 'running' WHERE id = ?", (j2,))
    db.commit()

    jobs = list_jobs(db, status="pending,running")
    assert len(jobs) == 2


# ---- _run_batch_job execution tests ----

class TestRunBatchJob:
    """Tests for _run_batch_job() execution.

    _run_batch_job uses ThreadPoolExecutor, so we need a thread-safe db helper.
    We use a file-based SQLite db with check_same_thread=False.
    """

    @pytest.fixture
    def tsdb(self, db, tmp_path, monkeypatch):
        """Create a thread-safe db setup for _run_batch_job tests."""
        import sqlite3
        from contextlib import contextmanager
        from open_uplift.db import SCHEMA_SQL, _seed_default_prompts, DEFAULT_PRICING
        from open_uplift.surveys import seed_default_config

        db_path = tmp_path / "threadtest.db"
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA_SQL)
        seed_default_config(conn)
        _seed_default_prompts(conn)
        for model_name, prices in DEFAULT_PRICING.items():
            conn.execute(
                """INSERT OR IGNORE INTO model_pricing
                   (model_name, input_cost_per_mtok, output_cost_per_mtok,
                    cache_read_per_mtok, cache_create_per_mtok)
                   VALUES (?, ?, ?, ?, ?)""",
                (model_name, prices["input"], prices["output"],
                 prices["cache_read"], prices["cache_create"]),
            )
        conn.commit()

        @contextmanager
        def _get_ts_db():
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        monkeypatch.setattr("open_uplift.job_queue.get_db", _get_ts_db)
        yield conn
        conn.close()

    def _insert_session(self, conn, session_id, msg_count=5):
        conn.execute(
            """INSERT INTO sessions
               (session_id, tool_source, started_at, message_count)
               VALUES (?, 'claude_code', '2026-01-01', ?)""",
            (session_id, msg_count),
        )
        conn.commit()

    def test_batch_job_processes_sessions(self, tsdb, monkeypatch):
        """Batch job runs scripts on sessions (mocked run_script)."""
        self._insert_session(tsdb, "s1")
        monkeypatch.setattr("open_uplift.job_queue.run_script", lambda db, sid, sess: {"status": "ok"})

        job_id = enqueue_job(tsdb, "script-batch", {"scripts": ["transcript-compact"], "session_ids": ["s1"]})
        tsdb.commit()

        _run_batch_job(job_id, {"scripts": ["transcript-compact"], "session_ids": ["s1"]})

        job = get_job(tsdb, job_id)
        assert job["status"] == "completed"

    def test_progress_updates(self, tsdb, monkeypatch):
        """Progress counters are updated during execution."""
        self._insert_session(tsdb, "s1")
        monkeypatch.setattr("open_uplift.job_queue.run_script", lambda db, sid, sess: {"status": "ok"})

        job_id = enqueue_job(tsdb, "script-batch", {"scripts": ["transcript-compact"], "session_ids": ["s1"]})
        tsdb.commit()

        _run_batch_job(job_id, {"scripts": ["transcript-compact"], "session_ids": ["s1"]})

        job = get_job(tsdb, job_id)
        assert job["progress"]["total"] == 1
        assert job["progress"]["completed"] == 1
        assert job["progress"]["failed"] == 0

    def test_failed_script_marks_session_failed_but_continues(self, tsdb, monkeypatch):
        """A script failure increments failed count but processing continues."""
        for sid in ["sess-a", "sess-b"]:
            self._insert_session(tsdb, sid)

        def fake_run(db, script_id, session_id):
            if session_id == "sess-a":
                return {"error": "Script failed"}
            return {"status": "ok"}

        monkeypatch.setattr("open_uplift.job_queue.run_script", fake_run)

        job_id = enqueue_job(tsdb, "batch", {"scripts": ["transcript-compact"], "session_ids": ["sess-a", "sess-b"]})
        tsdb.commit()

        _run_batch_job(job_id, {"scripts": ["transcript-compact"], "session_ids": ["sess-a", "sess-b"]})

        job = get_job(tsdb, job_id)
        assert job["status"] == "completed"
        assert job["progress"]["failed"] >= 1
        assert job["progress"]["completed"] == 2

    def test_status_transitions(self, tsdb, monkeypatch):
        """Job transitions: pending → running → completed."""
        self._insert_session(tsdb, "s1")
        statuses_seen = []

        def capture_run(db, script_id, session_id):
            job = get_job(tsdb, job_id)
            statuses_seen.append(job["status"])
            return {"status": "ok"}

        monkeypatch.setattr("open_uplift.job_queue.run_script", capture_run)

        job_id = enqueue_job(tsdb, "batch", {"scripts": ["transcript-compact"], "session_ids": ["s1"]})
        tsdb.commit()

        assert get_job(tsdb, job_id)["status"] == "pending"
        _run_batch_job(job_id, {"scripts": ["transcript-compact"], "session_ids": ["s1"]})
        assert get_job(tsdb, job_id)["status"] == "completed"
        assert "running" in statuses_seen

    def test_empty_session_list_completes(self, tsdb, monkeypatch):
        """Empty session list completes immediately."""
        job_id = enqueue_job(tsdb, "batch", {"scripts": ["transcript-compact"], "session_ids": []})
        tsdb.commit()

        _run_batch_job(job_id, {"scripts": ["transcript-compact"], "session_ids": []})
        job = get_job(tsdb, job_id)
        assert job["status"] == "completed"
        assert job["progress"]["total"] == 0

    def test_already_completed_script_is_skipped(self, tsdb, monkeypatch):
        """A script result already present and current should be skipped."""
        self._insert_session(tsdb, "s1")

        # Pre-insert completed result with matching message count
        tsdb.execute(
            """INSERT INTO script_results
               (session_id, script_id, status, started_at, completed_at, session_message_count)
               VALUES ('s1', 'transcript-compact', 'completed', '2026-01-01', '2026-01-01', 5)""",
        )
        tsdb.commit()

        run_calls = []
        def track_run(db, script_id, session_id):
            run_calls.append(script_id)
            return {"status": "ok"}

        monkeypatch.setattr("open_uplift.job_queue.run_script", track_run)

        job_id = enqueue_job(tsdb, "batch", {"scripts": ["transcript-compact"], "session_ids": ["s1"]})
        tsdb.commit()

        _run_batch_job(job_id, {"scripts": ["transcript-compact"], "session_ids": ["s1"]})

        # transcript-compact should be skipped, not called
        assert "transcript-compact" not in run_calls


class TestBatchCancellation:
    """Tests for cancellation during batch execution."""

    @pytest.fixture
    def tsdb(self, tmp_path, monkeypatch):
        """Thread-safe db for cancellation tests."""
        import sqlite3
        from contextlib import contextmanager
        from open_uplift.db import SCHEMA_SQL, _seed_default_prompts, DEFAULT_PRICING
        from open_uplift.surveys import seed_default_config

        db_path = tmp_path / "cancel_test.db"
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA_SQL)
        seed_default_config(conn)
        _seed_default_prompts(conn)
        for model_name, prices in DEFAULT_PRICING.items():
            conn.execute(
                """INSERT OR IGNORE INTO model_pricing
                   (model_name, input_cost_per_mtok, output_cost_per_mtok,
                    cache_read_per_mtok, cache_create_per_mtok)
                   VALUES (?, ?, ?, ?, ?)""",
                (model_name, prices["input"], prices["output"],
                 prices["cache_read"], prices["cache_create"]),
            )
        conn.commit()

        @contextmanager
        def _get_ts_db():
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        monkeypatch.setattr("open_uplift.job_queue.get_db", _get_ts_db)
        yield conn
        conn.close()

    def test_cancel_during_execution(self, tsdb, monkeypatch):
        """Cancelling after the first script prevents later scripts from running."""
        tsdb.execute(
            "INSERT INTO sessions (session_id, tool_source, started_at, message_count) VALUES ('c1', 'cc', '2026-01-01', 5)",
        )
        tsdb.commit()

        # Three scripts: cancel after the first, verify the third never runs
        job_id = enqueue_job(tsdb, "batch", {
            "scripts": ["transcript-compact", "llm-time-estimate", "judge"],
            "session_ids": ["c1"],
        })
        tsdb.commit()

        call_log = []
        def cancel_after_first(db_arg, script_id, session_id):
            call_log.append(script_id)
            if script_id == "transcript-compact":
                cancel_job(tsdb, job_id)
                tsdb.commit()
            return {"status": "ok"}

        monkeypatch.setattr("open_uplift.job_queue.run_script", cancel_after_first)

        _run_batch_job(job_id, {
            "scripts": ["transcript-compact", "llm-time-estimate", "judge"],
            "session_ids": ["c1"],
        })

        job = get_job(tsdb, job_id)
        assert job["status"] == "cancelled"
        # First script ran, but cancellation should stop before all three complete
        assert "transcript-compact" in call_log
        assert "judge" not in call_log

    def test_final_status_is_cancelled(self, tsdb, monkeypatch):
        """Final status should be 'cancelled' when cancelled between scripts."""
        tsdb.execute(
            "INSERT INTO sessions (session_id, tool_source, started_at, message_count) VALUES ('x1', 'cc', '2026-01-01', 5)"
        )
        tsdb.commit()

        # Two scripts so cancellation fires between them
        job_id = enqueue_job(tsdb, "batch", {
            "scripts": ["transcript-compact", "llm-time-estimate"],
            "session_ids": ["x1"],
        })
        tsdb.commit()

        def cancel_on_first_script(db_arg, script_id, session_id):
            if script_id == "transcript-compact":
                cancel_job(tsdb, job_id)
                tsdb.commit()
            return {"status": "ok"}

        monkeypatch.setattr("open_uplift.job_queue.run_script", cancel_on_first_script)

        _run_batch_job(job_id, {
            "scripts": ["transcript-compact", "llm-time-estimate"],
            "session_ids": ["x1"],
        })

        job = get_job(tsdb, job_id)
        assert job["status"] == "cancelled"


# ---- JobWorker tests ----

class TestJobWorker:
    """Tests for the JobWorker class."""

    @pytest.fixture
    def tsdb(self, tmp_path, monkeypatch):
        """Thread-safe db for worker tests."""
        import sqlite3
        from contextlib import contextmanager
        from open_uplift.db import SCHEMA_SQL, _seed_default_prompts, DEFAULT_PRICING
        from open_uplift.surveys import seed_default_config

        db_path = tmp_path / "worker_test.db"
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA_SQL)
        seed_default_config(conn)
        _seed_default_prompts(conn)
        for model_name, prices in DEFAULT_PRICING.items():
            conn.execute(
                """INSERT OR IGNORE INTO model_pricing
                   (model_name, input_cost_per_mtok, output_cost_per_mtok,
                    cache_read_per_mtok, cache_create_per_mtok)
                   VALUES (?, ?, ?, ?, ?)""",
                (model_name, prices["input"], prices["output"],
                 prices["cache_read"], prices["cache_create"]),
            )
        conn.commit()

        @contextmanager
        def _get_ts_db():
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        monkeypatch.setattr("open_uplift.job_queue.get_db", _get_ts_db)
        yield conn
        conn.close()

    def test_orphaned_jobs_reset_on_startup(self, tsdb):
        """Running jobs should be reset to pending on startup."""
        job_id = enqueue_job(tsdb, "batch", {"scripts": [], "session_ids": []})
        tsdb.execute("UPDATE jobs SET status = 'running' WHERE id = ?", (job_id,))
        tsdb.commit()
        assert get_job(tsdb, job_id)["status"] == "running"

        worker = JobWorker(poll_interval=0.1)
        worker.start()
        time.sleep(0.3)
        worker.stop()

        job = get_job(tsdb, job_id)
        assert job["status"] in ("pending", "completed", "failed")

    def test_worker_picks_up_pending_job(self, tsdb, monkeypatch):
        """Worker picks up and processes a pending job."""
        monkeypatch.setattr("open_uplift.job_queue.run_script", lambda db, sid, sess: {"status": "ok"})

        job_id = enqueue_job(tsdb, "batch", {"scripts": [], "session_ids": []})
        tsdb.commit()

        worker = JobWorker(poll_interval=0.1)
        worker.start()
        time.sleep(0.5)
        worker.stop()

        job = get_job(tsdb, job_id)
        assert job["status"] == "completed"

    def test_worker_stop_event_halts_polling(self, tsdb):
        """Setting the stop event should halt the worker."""
        worker = JobWorker(poll_interval=0.05)
        worker.start()
        assert worker._thread.is_alive()

        worker.stop()
        time.sleep(0.2)
        assert not worker._thread.is_alive()


# ---- Config migration tests ----

class TestRunModeConfig:
    """Tests for _get_run_mode_config and _set_run_mode_config."""

    def test_new_flat_format_reads_directly(self, db):
        """New flat format is read directly."""
        config = {"enabled": True, "start_hour": 5, "frequency_hours": 12.0}
        _set_run_mode_config(db, config)
        db.commit()

        result = _get_run_mode_config(db)
        assert result["enabled"] is True
        assert result["start_hour"] == 5
        assert result["frequency_hours"] == 12.0

    def test_old_scheduled_batch_format_migrates(self, db):
        """Old nested scheduled_batch format migrates to flat."""
        old_config = {
            "scheduled_batch": {
                "enabled": True,
                "mode": "daily",
                "daily_hour": 3,
            }
        }
        db.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES ('run_mode_config', ?)",
            (json.dumps(old_config),),
        )
        db.commit()

        result = _get_run_mode_config(db)
        assert result["enabled"] is True
        assert result["start_hour"] == 3
        assert result["frequency_hours"] == 24.0

    def test_old_interval_mode_migrates(self, db):
        """Old interval mode converts minutes to hours."""
        old_config = {
            "scheduled_batch": {
                "enabled": True,
                "mode": "interval",
                "interval_minutes": 120,
                "daily_hour": 2,
            }
        }
        db.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES ('run_mode_config', ?)",
            (json.dumps(old_config),),
        )
        db.commit()

        result = _get_run_mode_config(db)
        assert result["enabled"] is True
        assert result["frequency_hours"] == 2.0  # 120 minutes / 60

    def test_very_old_flat_format_migrates(self, db):
        """Very old auto_run_daily format migrates."""
        old_config = {
            "auto_run_daily": True,
            "daily_run_hour": 4,
        }
        db.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES ('run_mode_config', ?)",
            (json.dumps(old_config),),
        )
        db.commit()

        result = _get_run_mode_config(db)
        assert result["enabled"] is True
        assert result["start_hour"] == 4
        assert result["frequency_hours"] == 24.0

    def test_missing_config_returns_default(self, db):
        """Missing config key returns default config."""
        # Ensure no run_mode_config exists
        db.execute("DELETE FROM config WHERE key = 'run_mode_config'")
        db.commit()

        result = _get_run_mode_config(db)
        expected = _default_run_mode_config()
        assert result == expected
        assert result["enabled"] is False

    def test_set_and_get_round_trips(self, db):
        """_set_run_mode_config round-trips correctly."""
        config = {"enabled": True, "start_hour": 8, "frequency_hours": 6.0}
        _set_run_mode_config(db, config)
        db.commit()

        result = _get_run_mode_config(db)
        assert result == config


# ---- Scheduler timing tests ----

class TestSchedulerTiming:
    """Tests for BatchScheduler._schedule_next timing logic."""

    def test_delay_when_start_hour_in_future(self, db, monkeypatch):
        """When start_hour is later today, delay is computed correctly."""
        from open_uplift.job_queue import BatchScheduler
        from contextlib import contextmanager

        @contextmanager
        def _get_test_db():
            yield db
            db.commit()

        monkeypatch.setattr("open_uplift.job_queue.get_db", _get_test_db)

        _set_run_mode_config(db, {"enabled": True, "start_hour": 23, "frequency_hours": 24.0})
        db.commit()

        scheduler = BatchScheduler()
        timer_args = {}

        original_timer = threading.Timer
        def capture_timer(delay, func):
            timer_args["delay"] = delay
            t = original_timer(99999, func)  # Don't actually fire
            t.daemon = True
            return t

        monkeypatch.setattr("open_uplift.job_queue.threading.Timer", capture_timer)
        scheduler._schedule_next()

        assert "delay" in timer_args
        assert timer_args["delay"] > 0
        scheduler.stop()

    def test_disabled_config_produces_no_timer(self, db, monkeypatch):
        """Disabled config should not schedule a timer."""
        from open_uplift.job_queue import BatchScheduler
        from contextlib import contextmanager

        @contextmanager
        def _get_test_db():
            yield db
            db.commit()

        monkeypatch.setattr("open_uplift.job_queue.get_db", _get_test_db)

        _set_run_mode_config(db, {"enabled": False, "start_hour": 2, "frequency_hours": 24.0})
        db.commit()

        scheduler = BatchScheduler()
        scheduler._schedule_next()

        assert scheduler._timer is None
        scheduler.stop()

    def test_sub_day_intervals(self, db, monkeypatch):
        """frequency_hours < 24 produces sub-day intervals."""
        from open_uplift.job_queue import BatchScheduler
        from contextlib import contextmanager

        @contextmanager
        def _get_test_db():
            yield db
            db.commit()

        monkeypatch.setattr("open_uplift.job_queue.get_db", _get_test_db)

        _set_run_mode_config(db, {"enabled": True, "start_hour": 0, "frequency_hours": 6.0})
        db.commit()

        timer_args = {}
        original_timer = threading.Timer
        def capture_timer(delay, func):
            timer_args["delay"] = delay
            t = original_timer(99999, func)
            t.daemon = True
            return t

        monkeypatch.setattr("open_uplift.job_queue.threading.Timer", capture_timer)

        scheduler = BatchScheduler()
        scheduler._schedule_next()

        assert "delay" in timer_args
        # With 6h frequency, delay should be at most 6 hours = 21600 seconds
        assert timer_args["delay"] <= 6 * 3600 + 60  # small tolerance
        scheduler.stop()
