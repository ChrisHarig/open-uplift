"""Tests for time-with-AI measurement."""

import pytest

from open_uplift.time_measurement import compute_time_with_ai, compute_concurrency_adjustment


def test_compute_time_basic(db, sample_session):
    result = compute_time_with_ai(db, sample_session)
    assert result["active_minutes"] > 0
    assert result["total_windows"] >= 1
    assert result["active_windows"] >= 1
    assert result["first_message"] is not None
    assert result["last_message"] is not None


def test_compute_time_no_messages(db):
    result = compute_time_with_ai(db, "nonexistent-session")
    assert result["active_minutes"] == 0
    assert result["total_windows"] == 0
    assert result["active_windows"] == 0
    assert result["first_message"] is None


def test_ten_minute_bucketing(db):
    """Messages in different 10-min windows should count separately."""
    session_id = "test-bucket-session"
    db.execute(
        """INSERT INTO sessions
           (session_id, tool_source, started_at, message_count, scaffold)
           VALUES (?, 'claude_code', '2026-01-01T00:00:00Z', 4, 'claude_code')""",
        (session_id,),
    )
    # Messages at t=0, t=5min, t=15min, t=25min
    timestamps = [
        "2026-01-01T00:00:00+00:00",
        "2026-01-01T00:05:00+00:00",
        "2026-01-01T00:15:00+00:00",
        "2026-01-01T00:25:00+00:00",
    ]
    for ts in timestamps:
        db.execute(
            "INSERT INTO messages (session_id, timestamp, role) VALUES (?, ?, 'user')",
            (session_id, ts),
        )
    db.commit()

    result = compute_time_with_ai(db, session_id)
    # 0min and 5min are in window 0, 15min in window 1, 25min in window 2
    assert result["active_windows"] == 3
    assert result["active_minutes"] == 30  # 3 windows * 10 min


def test_single_message_session(db):
    session_id = "test-single-msg"
    db.execute(
        """INSERT INTO sessions
           (session_id, tool_source, started_at, message_count, scaffold)
           VALUES (?, 'claude_code', '2026-01-01T00:00:00Z', 1, 'claude_code')""",
        (session_id,),
    )
    db.execute(
        "INSERT INTO messages (session_id, timestamp, role) VALUES (?, '2026-01-01T00:00:00+00:00', 'user')",
        (session_id,),
    )
    db.commit()

    result = compute_time_with_ai(db, session_id)
    assert result["active_windows"] == 1
    assert result["active_minutes"] == 10


def test_assistant_only_messages(db):
    """Assistant-only messages should not create active windows."""
    session_id = "test-assistant-only"
    db.execute(
        """INSERT INTO sessions
           (session_id, tool_source, started_at, message_count, scaffold)
           VALUES (?, 'claude_code', '2026-01-01T00:00:00Z', 2, 'claude_code')""",
        (session_id,),
    )
    db.execute(
        "INSERT INTO messages (session_id, timestamp, role) VALUES (?, '2026-01-01T00:00:00+00:00', 'assistant')",
        (session_id,),
    )
    db.execute(
        "INSERT INTO messages (session_id, timestamp, role) VALUES (?, '2026-01-01T00:05:00+00:00', 'assistant')",
        (session_id,),
    )
    db.commit()

    result = compute_time_with_ai(db, session_id)
    assert result["active_windows"] == 0
    assert result["active_minutes"] == 0


def test_concurrency_no_overlap(db, sample_session):
    result = compute_concurrency_adjustment(db, sample_session)
    assert result["concurrent_sessions"] == 0
    assert result["raw_minutes"] == result["adjusted_minutes"]


def test_concurrency_with_overlap(db, sample_session):
    """Add an overlapping session and check concurrency adjustment."""
    db.execute(
        """INSERT INTO sessions
           (session_id, tool_source, started_at, ended_at, message_count, scaffold)
           VALUES ('overlap-1', 'claude_code', '2026-02-20T09:50:00Z', '2026-02-20T10:30:00Z', 5, 'claude_code')""",
    )
    db.commit()

    result = compute_concurrency_adjustment(db, sample_session)
    assert result["concurrent_sessions"] == 1
    assert result["adjusted_minutes"] < result["raw_minutes"]


def test_concurrency_nonexistent_session(db):
    result = compute_concurrency_adjustment(db, "nonexistent")
    assert result["raw_minutes"] == 0
    assert result["concurrent_sessions"] == 0
