"""Time-with-AI measurement using METR's 10-minute active window approach."""

import sqlite3
from datetime import datetime


WINDOW_SIZE_MINUTES = 10


def compute_time_with_ai(db: sqlite3.Connection, session_id: str) -> dict:
    """Compute active time with AI using 10-minute window approach.

    A window is 'active' if it contains >= 1 user message.
    This handles stepping away (idle windows don't count).
    """
    rows = db.execute(
        "SELECT timestamp, role FROM messages WHERE session_id = ? ORDER BY timestamp",
        (session_id,),
    ).fetchall()

    if not rows:
        return {
            "active_minutes": 0,
            "total_windows": 0,
            "active_windows": 0,
            "first_message": None,
            "last_message": None,
        }

    timestamps = []
    user_timestamps = []
    for r in rows:
        ts = _parse_ts(r["timestamp"])
        if ts:
            timestamps.append(ts)
            if r["role"] == "user":
                user_timestamps.append(ts)

    if not timestamps:
        return {
            "active_minutes": 0,
            "total_windows": 0,
            "active_windows": 0,
            "first_message": None,
            "last_message": None,
        }

    first = min(timestamps)
    last = max(timestamps)

    # Bucket into 10-minute windows from first message
    total_minutes = (last - first).total_seconds() / 60
    total_windows = max(1, int(total_minutes / WINDOW_SIZE_MINUTES) + 1)

    # Count active windows (those with at least one user message)
    active_window_set = set()
    for ts in user_timestamps:
        window_idx = int((ts - first).total_seconds() / (WINDOW_SIZE_MINUTES * 60))
        active_window_set.add(window_idx)

    active_windows = len(active_window_set)
    active_minutes = active_windows * WINDOW_SIZE_MINUTES

    return {
        "active_minutes": active_minutes,
        "total_windows": total_windows,
        "active_windows": active_windows,
        "first_message": first.isoformat(),
        "last_message": last.isoformat(),
    }


def compute_concurrency_adjustment(db: sqlite3.Connection, session_id: str) -> dict:
    """Find overlapping sessions and adjust active minutes for concurrency."""
    session = db.execute(
        "SELECT started_at, ended_at FROM sessions WHERE session_id = ?",
        (session_id,),
    ).fetchone()

    if not session:
        return {
            "raw_minutes": 0,
            "adjusted_minutes": 0,
            "concurrent_sessions": 0,
        }

    time_data = compute_time_with_ai(db, session_id)
    raw_minutes = time_data["active_minutes"]

    if not session["started_at"]:
        return {
            "raw_minutes": raw_minutes,
            "adjusted_minutes": raw_minutes,
            "concurrent_sessions": 0,
        }

    # Find sessions that overlap with this one's time range
    overlapping = db.execute(
        """SELECT session_id FROM sessions
           WHERE session_id != ?
             AND started_at <= ?
             AND (ended_at >= ? OR ended_at IS NULL)""",
        (
            session_id,
            session["ended_at"] or session["started_at"],
            session["started_at"],
        ),
    ).fetchall()

    concurrent_count = len(overlapping)
    divisor = 1 + concurrent_count
    adjusted_minutes = round(raw_minutes / divisor, 1)

    return {
        "raw_minutes": raw_minutes,
        "adjusted_minutes": adjusted_minutes,
        "concurrent_sessions": concurrent_count,
    }


def _parse_ts(ts_str: str) -> datetime | None:
    """Parse an ISO timestamp string."""
    if not ts_str:
        return None
    try:
        # Handle various ISO formats
        ts_str = ts_str.replace("Z", "+00:00")
        return datetime.fromisoformat(ts_str)
    except (ValueError, TypeError):
        return None
