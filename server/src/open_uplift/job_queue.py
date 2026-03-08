"""Async job queue for batch script execution."""

import json
import logging
import sqlite3
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from open_uplift.db import get_db
from open_uplift.scripts import run_script

logger = logging.getLogger(__name__)

# Module-level references set by start_worker / start_scheduler
_worker: "JobWorker | None" = None
_scheduler: "BatchScheduler | None" = None


def enqueue_job(db: sqlite3.Connection, job_type: str, payload: dict) -> str:
    """Insert a new job and return its UUID."""
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        """INSERT INTO jobs (id, job_type, status, payload, progress, created_at)
           VALUES (?, ?, 'pending', ?, '{}', ?)""",
        (job_id, job_type, json.dumps(payload), now),
    )
    return job_id


def get_job(db: sqlite3.Connection, job_id: str) -> dict | None:
    """Get a job by ID."""
    row = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["payload"] = json.loads(d["payload"])
    d["progress"] = json.loads(d["progress"])
    return d


def list_jobs(db: sqlite3.Connection, status: str | None = None, limit: int = 50) -> list[dict]:
    """List recent jobs, optionally filtered by status."""
    if status:
        statuses = [s.strip() for s in status.split(",")]
        placeholders = ",".join("?" for _ in statuses)
        rows = db.execute(
            f"SELECT * FROM jobs WHERE status IN ({placeholders}) ORDER BY created_at DESC LIMIT ?",
            (*statuses, limit),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    results = []
    for row in rows:
        d = dict(row)
        d["payload"] = json.loads(d["payload"])
        d["progress"] = json.loads(d["progress"])
        results.append(d)
    return results


def cancel_job(db: sqlite3.Connection, job_id: str) -> bool:
    """Mark a job as cancelled. Returns True if the job was found and cancellable."""
    row = db.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        return False
    if row["status"] in ("completed", "failed", "cancelled"):
        return False
    db.execute("UPDATE jobs SET status = 'cancelled' WHERE id = ?", (job_id,))
    return True


def _run_batch_job(job_id: str, payload: dict) -> None:
    """Execute a batch job: run scripts on sessions in parallel."""
    scripts = payload.get("scripts", ["transcript-compact", "llm-time-estimate"])
    session_ids = payload.get("session_ids", [])
    total = len(session_ids)

    with get_db() as db:
        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            "UPDATE jobs SET status = 'running', started_at = ?, progress = ? WHERE id = ?",
            (now, json.dumps({"total": total, "completed": 0, "failed": 0, "current_session_id": None, "last_error": None}), job_id),
        )

    progress_lock = threading.Lock()
    counters = {"completed": 0, "failed": 0, "cancelled": False, "last_error": None}

    def _update_progress():
        try:
            with get_db() as db:
                db.execute(
                    "UPDATE jobs SET progress = ? WHERE id = ?",
                    (json.dumps({"total": total, "completed": counters["completed"], "failed": counters["failed"], "current_session_id": None, "last_error": counters["last_error"]}), job_id),
                )
        except Exception as e:
            logger.warning("Failed to update job progress: %s", e)

    def _is_cancelled():
        try:
            with get_db() as db:
                row = db.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
                return row and row["status"] == "cancelled"
        except Exception:
            return False

    def _process_session(sid: str):
        if counters["cancelled"]:
            return
        if _is_cancelled():
            counters["cancelled"] = True
            return

        session_failed = False
        for script_id in scripts:
            # Check cancellation between scripts (e.g. skip judge if cancelled during compact)
            if counters["cancelled"] or _is_cancelled():
                counters["cancelled"] = True
                break

            # Skip if this script is already current for this session
            try:
                with get_db() as db:
                    row = db.execute(
                        """SELECT 1 FROM script_results sr
                           JOIN sessions s ON s.session_id = sr.session_id
                           WHERE sr.session_id = ? AND sr.script_id = ?
                             AND sr.status = 'completed'
                             AND sr.session_message_count >= s.message_count""",
                        (sid, script_id),
                    ).fetchone()
                    if row:
                        logger.info("Skipping %s for %s (already current)", script_id, sid)
                        continue
            except Exception:
                pass  # proceed with run if check fails

            try:
                with get_db() as db:
                    # Autocommit: don't hold a transaction open during LLM calls.
                    # Each SQL statement commits immediately, avoiding write lock
                    # contention between parallel workers.
                    db.isolation_level = None
                    result = run_script(db, script_id, sid)
                if "error" in result:
                    logger.warning("Script %s failed for %s: %s", script_id, sid, result["error"])
                    session_failed = True
                    counters["last_error"] = result["error"]
            except Exception as e:
                logger.error("Script %s crashed for %s: %s", script_id, sid, e)
                session_failed = True
                counters["last_error"] = str(e)

        with progress_lock:
            if session_failed:
                counters["failed"] += 1
            counters["completed"] += 1
            _update_progress()

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_process_session, sid) for sid in session_ids]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception:
                pass
            # Cancel queued futures when cancellation is detected
            if counters["cancelled"]:
                for f in futures:
                    f.cancel()
                break

    # Mark complete
    with get_db() as db:
        now = datetime.now(timezone.utc).isoformat()
        final_status = "cancelled" if counters["cancelled"] else "completed"
        db.execute(
            "UPDATE jobs SET status = ?, completed_at = ?, progress = ? WHERE id = ? AND status IN ('running', 'cancelled')",
            (final_status, now, json.dumps({"total": total, "completed": counters["completed"], "failed": counters["failed"], "current_session_id": None, "last_error": counters["last_error"]}), job_id),
        )


class JobWorker:
    """Daemon thread that polls for pending jobs and processes them sequentially."""

    def __init__(self, poll_interval: float = 2.0):
        self.poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="job-worker")
        self._thread.start()
        logger.info("Job worker started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)
        logger.info("Job worker stopped")

    def _run(self) -> None:
        # Reset orphaned running jobs on startup
        try:
            with get_db() as db:
                db.execute("UPDATE jobs SET status = 'pending' WHERE status = 'running'")
        except Exception as e:
            logger.error("Failed to reset orphaned jobs: %s", e)

        while not self._stop_event.is_set():
            try:
                with get_db() as db:
                    row = db.execute(
                        "SELECT id, payload FROM jobs WHERE status = 'pending' ORDER BY created_at ASC LIMIT 1"
                    ).fetchone()

                if row:
                    job_id = row["id"]
                    payload = json.loads(row["payload"])
                    logger.info("Processing job %s", job_id)
                    try:
                        _run_batch_job(job_id, payload)
                    except Exception as e:
                        logger.error("Job %s failed: %s", job_id, e)
                        with get_db() as db:
                            now = datetime.now(timezone.utc).isoformat()
                            db.execute(
                                "UPDATE jobs SET status = 'failed', error = ?, completed_at = ? WHERE id = ?",
                                (str(e), now, job_id),
                            )
                else:
                    self._stop_event.wait(self.poll_interval)
            except Exception as e:
                logger.error("Job worker error: %s", e)
                self._stop_event.wait(self.poll_interval)


class BatchScheduler:
    """Timer that fires on a configurable schedule to sync and enqueue unprocessed session batches."""

    def __init__(self):
        self._timer: threading.Timer | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        self._stop_event.clear()
        self._schedule_next()

    def stop(self) -> None:
        self._stop_event.set()
        if self._timer:
            self._timer.cancel()

    def reschedule(self) -> None:
        if self._timer:
            self._timer.cancel()
        self._schedule_next()

    def _schedule_next(self) -> None:
        if self._stop_event.is_set():
            return
        try:
            with get_db() as db:
                config = _get_run_mode_config(db)
        except Exception:
            config = _default_run_mode_config()

        if not config.get("enabled"):
            return

        from datetime import timedelta

        start_hour = config.get("start_hour", 2)
        frequency_hours = config.get("frequency_hours", 24.0)

        now = datetime.now()
        # Find the next run time: start from today's start_hour, step by frequency_hours
        target = now.replace(hour=start_hour, minute=0, second=0, microsecond=0)
        if target > now:
            # Next run is today's start_hour
            pass
        else:
            # Advance by frequency_hours until we're in the future
            freq_delta = timedelta(hours=frequency_hours)
            while target <= now:
                target += freq_delta

        delay = (target - now).total_seconds()
        self._timer = threading.Timer(delay, self._fire)
        self._timer.daemon = True
        self._timer.start()
        logger.info("Batch scheduler: next run in %.0f seconds (every %.1fh from %02d:00)", delay, frequency_hours, start_hour)

    def _fire(self) -> None:
        if self._stop_event.is_set():
            return
        logger.info("Batch scheduler firing")
        try:
            _sync_and_enqueue()
        except Exception as e:
            logger.error("Batch scheduler error: %s", e)
        self._schedule_next()


def _default_run_mode_config() -> dict:
    return {
        "enabled": False,
        "start_hour": 2,
        "frequency_hours": 24.0,
    }


def _get_run_mode_config(db: sqlite3.Connection) -> dict:
    """Get run mode config from the config table."""
    row = db.execute("SELECT value FROM config WHERE key = 'run_mode_config'").fetchone()
    if row:
        config = json.loads(row["value"])
        # Migrate old nested scheduled_batch shape to new flat shape
        if "scheduled_batch" in config:
            batch = config["scheduled_batch"]
            mode = batch.get("mode", "daily")
            if mode == "daily":
                freq = 24.0
            else:
                freq = batch.get("interval_minutes", 60) / 60.0
            config = {
                "enabled": batch.get("enabled", False),
                "start_hour": batch.get("daily_hour", 2),
                "frequency_hours": freq,
            }
        # Migrate very old flat config
        elif "auto_run_daily" in config:
            config = {
                "enabled": config.get("auto_run_daily", False),
                "start_hour": config.get("daily_run_hour", 2),
                "frequency_hours": 24.0,
            }
        return config
    return _default_run_mode_config()


def _set_run_mode_config(db: sqlite3.Connection, config: dict) -> None:
    """Store run mode config."""
    db.execute(
        "INSERT OR REPLACE INTO config (key, value) VALUES ('run_mode_config', ?)",
        (json.dumps(config),),
    )


def _find_unprocessed_session_ids(
    db: sqlite3.Connection,
    scripts: list[str] | None = None,
    require_survey: bool = False,
) -> list[str]:
    """Find sessions missing completed script results for any of the given scripts.

    When require_survey=True (legacy behavior), only considers sessions with survey responses.
    When require_survey=False (default), considers ALL sessions.
    """
    if scripts is None:
        scripts = ["transcript-compact", "llm-time-estimate"]

    placeholders = ",".join("?" for _ in scripts)
    if require_survey:
        rows = db.execute(
            f"""SELECT DISTINCT sr.session_id
                FROM survey_responses sr
                WHERE sr.session_id IS NOT NULL
                  AND sr.session_id NOT IN (
                      SELECT session_id FROM script_results
                      WHERE script_id IN ({placeholders}) AND status = 'completed'
                      GROUP BY session_id
                      HAVING COUNT(DISTINCT script_id) = ?
                  )
                ORDER BY sr.timestamp ASC""",
            (*scripts, len(scripts)),
        ).fetchall()
    else:
        rows = db.execute(
            f"""SELECT DISTINCT s.session_id
                FROM sessions s
                WHERE s.session_id NOT IN (
                    SELECT session_id FROM script_results
                    WHERE script_id IN ({placeholders}) AND status = 'completed'
                    GROUP BY session_id
                    HAVING COUNT(DISTINCT script_id) = ?
                )
                ORDER BY s.started_at ASC""",
            (*scripts, len(scripts)),
        ).fetchall()
    return [r["session_id"] for r in rows]


def _enqueue_unprocessed() -> tuple[str, int]:
    """Find unprocessed sessions and enqueue a batch job. Returns (job_id, count)."""
    scripts = ["transcript-compact", "llm-time-estimate"]
    with get_db() as db:
        session_ids = _find_unprocessed_session_ids(db, scripts)
        if not session_ids:
            return ("", 0)
        job_id = enqueue_job(db, "daily-batch", {"scripts": scripts, "session_ids": session_ids})
    return (job_id, len(session_ids))


def _sync_and_enqueue() -> tuple[str, int]:
    """Sync session data, then find unprocessed sessions and enqueue a batch job."""
    from open_uplift.ingest import sync_all
    try:
        sync_all()
    except Exception as e:
        logger.error("Sync failed during scheduled batch: %s", e)

    return _enqueue_unprocessed()


def start_worker() -> None:
    """Start the global job worker."""
    global _worker
    if _worker is None:
        _worker = JobWorker()
    _worker.start()


def start_scheduler() -> None:
    """Start the batch scheduler if enabled in config."""
    global _scheduler
    if _scheduler is None:
        _scheduler = BatchScheduler()
    try:
        with get_db() as db:
            config = _get_run_mode_config(db)
        if config.get("enabled"):
            _scheduler.start()
            _maybe_run_catchup(db, config)
    except Exception as e:
        logger.warning("Could not start batch scheduler: %s", e)


def _maybe_run_catchup(db: sqlite3.Connection, config: dict) -> None:
    """If scheduled batch is enabled and last run was too long ago, enqueue immediately."""
    from datetime import timedelta

    frequency_hours = config.get("frequency_hours", 24.0)

    last = db.execute(
        "SELECT MAX(created_at) as last_run FROM jobs WHERE job_type = 'daily-batch'"
    ).fetchone()
    if last and last["last_run"]:
        last_dt = datetime.fromisoformat(last["last_run"])
        if datetime.now(timezone.utc) - last_dt < timedelta(hours=frequency_hours):
            return
    # Either no previous run or stale
    scripts = ["transcript-compact", "llm-time-estimate"]
    session_ids = _find_unprocessed_session_ids(db, scripts)
    if session_ids:
        enqueue_job(db, "daily-batch", {"scripts": scripts, "session_ids": session_ids})
        logger.info("Catch-up batch enqueued for %d sessions", len(session_ids))


class SyncScheduler:
    """Timer that fires on a configurable schedule to sync org memberships."""

    def __init__(self, interval_seconds: float = 1800):
        self._interval = interval_seconds  # default 30 minutes
        self._timer: threading.Timer | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        self._stop_event.clear()
        self._schedule_next()

    def stop(self) -> None:
        self._stop_event.set()
        if self._timer:
            self._timer.cancel()

    def _schedule_next(self) -> None:
        if self._stop_event.is_set():
            return
        self._timer = threading.Timer(self._interval, self._fire)
        self._timer.daemon = True
        self._timer.start()
        logger.info("Sync scheduler: next run in %.0f seconds", self._interval)

    def _fire(self) -> None:
        if self._stop_event.is_set():
            return
        logger.info("Sync scheduler firing")
        try:
            from open_uplift.sync import sync_all_orgs
            sync_all_orgs()
        except Exception as e:
            logger.error("Sync scheduler error: %s", e)
        self._schedule_next()


_sync_scheduler: "SyncScheduler | None" = None


def start_sync_scheduler() -> None:
    """Start the org sync scheduler if any memberships exist."""
    global _sync_scheduler
    if _sync_scheduler is None:
        _sync_scheduler = SyncScheduler()
    try:
        with get_db() as db:
            count = db.execute("SELECT COUNT(*) as c FROM org_memberships").fetchone()
        if count and count["c"] > 0:
            _sync_scheduler.start()
    except Exception as e:
        logger.warning("Could not start sync scheduler: %s", e)


def update_scheduler_config() -> None:
    """Called when run_mode_config changes to start/stop/reschedule the batch scheduler."""
    global _scheduler
    if _scheduler is None:
        _scheduler = BatchScheduler()
    try:
        with get_db() as db:
            config = _get_run_mode_config(db)
        if config.get("enabled"):
            _scheduler.start()
            _scheduler.reschedule()
        else:
            _scheduler.stop()
    except Exception as e:
        logger.warning("Could not update scheduler: %s", e)
