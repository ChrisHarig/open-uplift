import logging
import sqlite3
from datetime import datetime, timezone

from open_uplift.db import get_db
from open_uplift.providers import get_all_providers

logger = logging.getLogger(__name__)


def calculate_cost(
    db: sqlite3.Connection,
    model: str | None,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    cache_create_tokens: int,
) -> float:
    """Calculate USD cost for a single API call using model_pricing table."""
    if not model:
        return 0.0
    row = db.execute(
        "SELECT * FROM model_pricing WHERE ? LIKE model_name || '%'",
        (model,),
    ).fetchone()
    if not row:
        return 0.0
    cost = (
        (input_tokens * row["input_cost_per_mtok"])
        + (output_tokens * row["output_cost_per_mtok"])
        + (cache_read_tokens * (row["cache_read_per_mtok"] or 0))
        + (cache_create_tokens * (row["cache_create_per_mtok"] or 0))
    ) / 1_000_000
    return round(cost, 6)


def sync_all() -> dict:
    """Ingest new data from all providers. Returns stats."""
    stats = {"sessions_new": 0, "sessions_updated": 0, "messages_added": 0}

    with get_db() as db:
        for provider in get_all_providers():
            for file_path in provider.discover_session_files():
                path_str = str(file_path)

                # Check previous ingestion offset
                row = db.execute(
                    "SELECT byte_offset FROM ingest_log WHERE file_path = ?",
                    (path_str,),
                ).fetchone()
                prev_offset = row["byte_offset"] if row else 0

                # Check if file has grown
                file_size = file_path.stat().st_size
                if file_size <= prev_offset:
                    continue

                # Parse new content
                session, messages, new_offset = provider.parse_session(
                    file_path, from_offset=prev_offset
                )

                if not messages:
                    continue

                # Calculate costs for each message
                for msg in messages:
                    if msg.role == "assistant":
                        msg.cost_usd = calculate_cost(
                            db,
                            msg.model,
                            msg.input_tokens,
                            msg.output_tokens,
                            msg.cache_read_tokens,
                            msg.cache_create_tokens,
                        )

                # Upsert session
                existing = db.execute(
                    "SELECT session_id FROM sessions WHERE session_id = ?",
                    (session.session_id,),
                ).fetchone()

                total_input = sum(m.input_tokens for m in messages)
                total_output = sum(m.output_tokens for m in messages)
                total_cache_read = sum(m.cache_read_tokens for m in messages)
                total_cache_create = sum(m.cache_create_tokens for m in messages)
                total_cost = sum(m.cost_usd for m in messages)

                if existing:
                    now_ts = datetime.now(timezone.utc).isoformat()
                    db.execute(
                        """UPDATE sessions SET
                           ended_at = ?,
                           total_input_tokens = total_input_tokens + ?,
                           total_output_tokens = total_output_tokens + ?,
                           total_cache_read_tokens = total_cache_read_tokens + ?,
                           total_cache_create_tokens = total_cache_create_tokens + ?,
                           total_cost_usd = total_cost_usd + ?,
                           message_count = message_count + ?,
                           tool_call_count = tool_call_count + ?,
                           model_primary = COALESCE(?, model_primary),
                           updated_at = ?
                           WHERE session_id = ?""",
                        (
                            session.ended_at,
                            total_input,
                            total_output,
                            total_cache_read,
                            total_cache_create,
                            total_cost,
                            len(messages),
                            session.tool_call_count,
                            session.model_primary,
                            now_ts,
                            session.session_id,
                        ),
                    )
                    stats["sessions_updated"] += 1
                else:
                    session.total_input_tokens = total_input
                    session.total_output_tokens = total_output
                    session.total_cache_read_tokens = total_cache_read
                    session.total_cache_create_tokens = total_cache_create
                    session.total_cost_usd = total_cost
                    session.message_count = len(messages)

                    now_ts = datetime.now(timezone.utc).isoformat()
                    db.execute(
                        """INSERT INTO sessions
                           (session_id, tool_source, project_path, project_name, git_branch,
                            started_at, ended_at, total_input_tokens, total_output_tokens,
                            total_cache_read_tokens, total_cache_create_tokens,
                            total_cost_usd, message_count, tool_call_count, model_primary, scaffold,
                            updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            session.session_id,
                            session.tool_source,
                            session.project_path,
                            session.project_name,
                            session.git_branch,
                            session.started_at,
                            session.ended_at,
                            session.total_input_tokens,
                            session.total_output_tokens,
                            session.total_cache_read_tokens,
                            session.total_cache_create_tokens,
                            session.total_cost_usd,
                            session.message_count,
                            session.tool_call_count,
                            session.model_primary,
                            provider.scaffold_name,
                            now_ts,
                        ),
                    )
                    stats["sessions_new"] += 1

                # Insert messages
                for msg in messages:
                    db.execute(
                        """INSERT INTO messages
                           (session_id, request_id, timestamp, role, model,
                            input_tokens, output_tokens, cache_read_tokens,
                            cache_create_tokens, cost_usd, tool_names)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            msg.session_id,
                            msg.request_id,
                            msg.timestamp,
                            msg.role,
                            msg.model,
                            msg.input_tokens,
                            msg.output_tokens,
                            msg.cache_read_tokens,
                            msg.cache_create_tokens,
                            msg.cost_usd,
                            msg.tool_names,
                        ),
                    )
                stats["messages_added"] += len(messages)

                # Update ingest log
                now = datetime.now(timezone.utc).isoformat()
                db.execute(
                    """INSERT INTO ingest_log (file_path, byte_offset, last_synced)
                       VALUES (?, ?, ?)
                       ON CONFLICT(file_path) DO UPDATE SET
                           byte_offset = excluded.byte_offset,
                           last_synced = excluded.last_synced""",
                    (path_str, new_offset, now),
                )

    # Post-ingestion: link continuation sessions
    with get_db() as db:
        link_continuation_sessions(db)

    return stats


def link_continuation_sessions(db: sqlite3.Connection) -> int:
    """Detect and link continuation sessions based on time proximity.

    For each consecutive pair of sessions from the same project where B starts
    within 5 minutes of A ending, parse A's transcript to determine the
    continuation type and link B to A.

    Returns number of sessions linked.
    """
    # Get candidate sessions ordered by project and start time
    # Only consider sessions not already linked
    rows = db.execute(
        """SELECT session_id, project_path, started_at, ended_at
           FROM sessions
           WHERE project_path IS NOT NULL
           ORDER BY project_path, started_at"""
    ).fetchall()

    if not rows:
        return 0

    linked = 0
    prev = None
    for row in rows:
        if prev and prev["project_path"] == row["project_path"]:
            # Check if B (row) starts within 5 minutes of A (prev) ending
            if prev["ended_at"] and row["started_at"]:
                try:
                    a_end = datetime.fromisoformat(prev["ended_at"])
                    b_start = datetime.fromisoformat(row["started_at"])
                    gap = (b_start - a_end).total_seconds()
                    if 0 <= gap <= 300:  # within 5 minutes
                        # Check if already linked
                        existing = db.execute(
                            "SELECT continued_from FROM sessions WHERE session_id = ?",
                            (row["session_id"],),
                        ).fetchone()
                        if existing and existing["continued_from"]:
                            prev = row
                            continue

                        # Parse predecessor's transcript to determine type
                        continuation_type = _detect_continuation_type(db, prev["session_id"])
                        db.execute(
                            "UPDATE sessions SET continued_from = ?, continuation_type = ? WHERE session_id = ?",
                            (prev["session_id"], continuation_type, row["session_id"]),
                        )
                        linked += 1
                except (ValueError, TypeError):
                    pass
        prev = row

    return linked


def _detect_continuation_type(db: sqlite3.Connection, session_id: str) -> str:
    """Determine the continuation type by parsing the predecessor's transcript."""
    from open_uplift.scripts import _get_transcript_path
    from open_uplift.transcript import detect_session_end_type, parse_transcript

    path = _get_transcript_path(db, session_id)
    if not path:
        return "general"

    try:
        transcript_data = parse_transcript(path)
        end_type = detect_session_end_type(transcript_data)
        if end_type == "plan":
            return "plan"
        return "general"
    except Exception:
        logger.warning("Failed to parse transcript for session %s", session_id, exc_info=True)
        return "general"
