"""Client-side org sync logic: join, push, pull data via HTTP hub server."""

import json
import logging
import sqlite3
from datetime import datetime, timezone

import requests

from open_uplift.config import DEFAULT_SHARING_CONFIG
from open_uplift.db import get_db

logger = logging.getLogger(__name__)


def join_org(db: sqlite3.Connection, hub_url: str, invite_code: str, member_name: str) -> dict:
    """Join an org by posting an invite code to the hub server."""
    url = f"{hub_url.rstrip('/')}/hub/join"
    resp = requests.post(url, json={"invite_code": invite_code, "member_name": member_name}, timeout=30)
    if resp.status_code != 201:
        error = resp.json().get("error", resp.text) if resp.headers.get("content-type", "").startswith("application/json") else resp.text
        raise RuntimeError(f"Join failed ({resp.status_code}): {error}")

    data = resp.json()
    org_id = data["org_id"]
    org_name = data.get("org_name", org_id)
    api_key = data["api_key"]
    sharing_config = data.get("sharing_config", DEFAULT_SHARING_CONFIG)

    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        """INSERT INTO org_memberships
           (org_id, org_name, member_name, role, hub_url, api_key,
            sharing_config, joined_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(org_id) DO UPDATE SET
               hub_url = excluded.hub_url,
               api_key = excluded.api_key,
               sharing_config = excluded.sharing_config,
               org_name = excluded.org_name""",
        (
            org_id,
            org_name,
            member_name,
            data.get("role", "member"),
            hub_url.rstrip("/"),
            api_key,
            json.dumps(sharing_config),
            now,
        ),
    )

    # Create a local organization record so it appears in the orgs list
    db.execute(
        """INSERT INTO organizations (org_id, name, description, is_verified, created_at, sharing_config, org_mode)
           VALUES (?, ?, ?, 0, ?, ?, 'member')
           ON CONFLICT(org_id) DO UPDATE SET
               name = excluded.name,
               org_mode = 'member'""",
        (org_id, org_name, f"Connected to hub: {hub_url.rstrip('/')}", now, json.dumps(sharing_config)),
    )

    return {
        "org_id": org_id,
        "org_name": org_name,
        "sharing_config": sharing_config,
    }


def _gather_aggregate(db: sqlite3.Connection, sharing_config: dict, org_id: str | None = None) -> dict:
    """Compute aggregate stats from local judged sessions in org folders."""
    stats_config = sharing_config.get("stats", {})
    result = {}

    # Build org folder filter
    path_filter = ""
    path_params: list = []
    if org_id:
        folder_paths = [
            r["folder_path"]
            for r in db.execute("SELECT folder_path FROM org_folders WHERE org_id = ?", (org_id,)).fetchall()
        ]
        if folder_paths:
            path_conds = " OR ".join(
                ["(s.project_path = ? OR s.project_path LIKE ? || '/%')"] * len(folder_paths)
            )
            path_filter = f" AND ({path_conds})"
            for fp in folder_paths:
                path_params.extend([fp, fp])

    # Only count judged sessions (have completed llm-time-estimate with current message count)
    totals = db.execute(
        f"""SELECT
             COUNT(*) as total_sessions,
             COALESCE(SUM(s.total_input_tokens + s.total_output_tokens), 0) as total_tokens,
             COALESCE(SUM(s.total_cost_usd), 0) as total_cost_usd,
             COALESCE(SUM(s.message_count), 0) as total_messages,
             COALESCE(SUM(s.tool_call_count), 0) as total_tool_calls
           FROM sessions s
           JOIN script_results sr ON sr.session_id = s.session_id
               AND sr.script_id = 'llm-time-estimate'
               AND sr.status = 'completed'
               AND sr.session_message_count >= s.message_count
           WHERE COALESCE(s.is_local, 1) = 1
             {path_filter}""",
        path_params,
    ).fetchone()

    # Always include total_sessions (it's just a count, needed for aggregation)
    result["total_sessions"] = totals["total_sessions"]
    if stats_config.get("tokens"):
        result["total_tokens"] = totals["total_tokens"]
    if stats_config.get("cost"):
        result["total_cost_usd"] = totals["total_cost_usd"]
    if stats_config.get("messages"):
        result["total_messages"] = totals["total_messages"]
    if stats_config.get("tool_calls"):
        result["total_tool_calls"] = totals["total_tool_calls"]
    if stats_config.get("uplift"):
        uplift = db.execute(
            f"""SELECT AVG(uo.uplift_factor) as avg
               FROM uplift_outputs uo
               JOIN sessions s ON s.session_id = uo.session_id
               JOIN script_results sr ON sr.session_id = s.session_id
                   AND sr.script_id = 'llm-time-estimate'
                   AND sr.status = 'completed'
                   AND sr.session_message_count >= s.message_count
               WHERE uo.output_id = 'llm-judge'
                 AND COALESCE(s.is_local, 1) = 1
                 {path_filter}""",
            path_params,
        ).fetchone()
        result["avg_uplift_factor"] = uplift["avg"] if uplift else None

        # Per-scaffold breakdown
        scaffold_rows = db.execute(
            f"""SELECT COALESCE(s.scaffold, s.tool_source) as scaffold,
                       ROUND(AVG(uo.uplift_factor), 4) as avg_uplift,
                       COUNT(*) as count
               FROM uplift_outputs uo
               JOIN sessions s ON s.session_id = uo.session_id
               JOIN script_results sr ON sr.session_id = s.session_id
                   AND sr.script_id = 'llm-time-estimate'
                   AND sr.status = 'completed'
                   AND sr.session_message_count >= s.message_count
               WHERE uo.output_id = 'llm-judge'
                 AND COALESCE(s.is_local, 1) = 1
                 {path_filter}
               GROUP BY scaffold""",
            path_params,
        ).fetchall()
        result["by_scaffold"] = [dict(r) for r in scaffold_rows]

        # Per-model breakdown
        model_rows = db.execute(
            f"""SELECT s.model_primary as model,
                       ROUND(AVG(uo.uplift_factor), 4) as avg_uplift,
                       COUNT(*) as count
               FROM uplift_outputs uo
               JOIN sessions s ON s.session_id = uo.session_id
               JOIN script_results sr ON sr.session_id = s.session_id
                   AND sr.script_id = 'llm-time-estimate'
                   AND sr.status = 'completed'
                   AND sr.session_message_count >= s.message_count
               WHERE uo.output_id = 'llm-judge'
                 AND s.model_primary IS NOT NULL
                 AND COALESCE(s.is_local, 1) = 1
                 {path_filter}
               GROUP BY s.model_primary""",
            path_params,
        ).fetchall()
        result["by_model"] = [dict(r) for r in model_rows]

        # Raw uplift values for distribution
        value_rows = db.execute(
            f"""SELECT uo.uplift_factor
               FROM uplift_outputs uo
               JOIN sessions s ON s.session_id = uo.session_id
               JOIN script_results sr ON sr.session_id = s.session_id
                   AND sr.script_id = 'llm-time-estimate'
                   AND sr.status = 'completed'
                   AND sr.session_message_count >= s.message_count
               WHERE uo.output_id = 'llm-judge'
                 AND COALESCE(s.is_local, 1) = 1
                 {path_filter}""",
            path_params,
        ).fetchall()
        result["uplift_values"] = [r["uplift_factor"] for r in value_rows]

    return result


def _gather_sessions(db: sqlite3.Connection, sharing_config: dict, since: str | None, org_id: str | None = None) -> list[dict]:
    """Gather per-session data since last push."""
    stats_config = sharing_config.get("stats", {})
    level = sharing_config.get("level", 1)
    if level < 2:
        return []

    where = "WHERE COALESCE(s.is_local, 1) = 1"
    params: list = []
    if since:
        where += " AND s.updated_at > ?"
        params.append(since)

    # Filter to org's folders if org_id provided
    if org_id:
        folder_paths = [
            r["folder_path"]
            for r in db.execute("SELECT folder_path FROM org_folders WHERE org_id = ?", (org_id,)).fetchall()
        ]
        if folder_paths:
            path_conds = " OR ".join(
                ["(s.project_path = ? OR s.project_path LIKE ? || '/%')"] * len(folder_paths)
            )
            where += f" AND ({path_conds})"
            for fp in folder_paths:
                params.extend([fp, fp])

    rows = db.execute(
        f"""SELECT s.*, uo.uplift_factor
           FROM sessions s
           JOIN script_results sr ON sr.session_id = s.session_id
               AND sr.script_id = 'llm-time-estimate'
               AND sr.status = 'completed'
               AND sr.session_message_count >= s.message_count
           LEFT JOIN uplift_outputs uo ON s.session_id = uo.session_id AND uo.output_id = 'llm-judge'
           {where}
           ORDER BY s.started_at""",
        params,
    ).fetchall()

    sessions = []
    for row in rows:
        s: dict = {"session_id": row["session_id"], "started_at": row["started_at"], "ended_at": row["ended_at"]}
        s["model_primary"] = row["model_primary"]
        s["project_name"] = row["project_name"]
        s["scaffold"] = row["scaffold"] or row["tool_source"]
        if stats_config.get("tokens"):
            s["total_input_tokens"] = row["total_input_tokens"]
            s["total_output_tokens"] = row["total_output_tokens"]
            s["total_cache_read_tokens"] = row["total_cache_read_tokens"]
            s["total_cache_create_tokens"] = row["total_cache_create_tokens"]
        if stats_config.get("cost"):
            s["total_cost_usd"] = row["total_cost_usd"]
        if stats_config.get("messages"):
            s["message_count"] = row["message_count"]
        if stats_config.get("tool_calls"):
            s["tool_call_count"] = row["tool_call_count"]
        if stats_config.get("uplift"):
            s["uplift_factor"] = row["uplift_factor"]
        sessions.append(s)

    return sessions


def push_org(db: sqlite3.Connection, membership: dict) -> dict:
    """Push local aggregate + sessions to the hub server."""
    hub_url = membership.get("hub_url")
    api_key = membership.get("api_key")
    if not hub_url or not api_key:
        raise RuntimeError("No hub_url or api_key configured for this membership")

    sharing_config = json.loads(membership["sharing_config"]) if membership.get("sharing_config") else DEFAULT_SHARING_CONFIG
    aggregate = _gather_aggregate(db, sharing_config, org_id=membership.get("org_id"))
    sessions = _gather_sessions(db, sharing_config, membership.get("last_push_at"), org_id=membership.get("org_id"))

    url = f"{hub_url}/hub/push"
    resp = requests.post(
        url,
        json={"aggregate": aggregate, "sessions": sessions},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=60,
    )
    if resp.status_code != 200:
        error = resp.json().get("error", resp.text) if resp.headers.get("content-type", "").startswith("application/json") else resp.text
        raise RuntimeError(f"Push failed ({resp.status_code}): {error}")

    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "UPDATE org_memberships SET last_push_at = ? WHERE org_id = ?",
        (now, membership["org_id"]),
    )

    result = resp.json()
    result["received_sessions"] = len(sessions)
    return result


def pull_org(db: sqlite3.Connection, membership: dict) -> dict:
    """Pull aggregate + sessions from other members via the hub server."""
    hub_url = membership.get("hub_url")
    api_key = membership.get("api_key")
    if not hub_url or not api_key:
        raise RuntimeError("No hub_url or api_key configured for this membership")

    params = {}
    if membership.get("last_pull_at"):
        params["since"] = membership["last_pull_at"]

    url = f"{hub_url}/hub/pull"
    resp = requests.get(
        url,
        params=params,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=60,
    )
    if resp.status_code != 200:
        error = resp.json().get("error", resp.text) if resp.headers.get("content-type", "").startswith("application/json") else resp.text
        raise RuntimeError(f"Pull failed ({resp.status_code}): {error}")

    data = resp.json()

    # Update membership record
    now = datetime.now(timezone.utc).isoformat()
    new_sharing = data.get("sharing_config")
    if new_sharing:
        db.execute(
            "UPDATE org_memberships SET sharing_config = ?, last_pull_at = ? WHERE org_id = ?",
            (json.dumps(new_sharing), now, membership["org_id"]),
        )
    else:
        db.execute(
            "UPDATE org_memberships SET last_pull_at = ? WHERE org_id = ?",
            (now, membership["org_id"]),
        )

    # Cache aggregate in config table
    org_id = membership["org_id"]
    from open_uplift.surveys import _set_config
    cache_key = f"org_aggregate_{org_id}"
    _set_config(db, cache_key, {
        "aggregate": data.get("aggregate"),
        "org_name": data.get("org_name", ""),
        "pulled_at": now,
        "members": data.get("members", []),
    })

    # Store pulled sessions locally when sharing level >= 2
    # Use pull_config if set (member preferences), otherwise fall back to sharing_config
    pulled_sessions = data.get("sessions", [])
    stored_count = 0
    current_sharing = new_sharing or (json.loads(membership["sharing_config"]) if membership.get("sharing_config") else DEFAULT_SHARING_CONFIG)
    pull_config = json.loads(membership["pull_config"]) if membership.get("pull_config") else None
    effective_config = pull_config or current_sharing
    if effective_config.get("level", 1) >= 2 and pulled_sessions:
        stats_config = effective_config.get("stats", {})
        for sess in pulled_sessions:
            sid = sess.get("session_id")
            if not sid:
                continue
            member_name = sess.get("member_name", "")
            db.execute(
                """INSERT INTO sessions
                   (session_id, started_at, ended_at, model_primary, project_name,
                    scaffold, total_input_tokens, total_output_tokens,
                    total_cache_read_tokens, total_cache_create_tokens,
                    total_cost_usd, message_count, tool_call_count,
                    is_local, source_member, source_org_id, updated_at, tool_source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, 'claude_code')
                   ON CONFLICT(session_id) DO UPDATE SET
                       started_at = excluded.started_at,
                       ended_at = excluded.ended_at,
                       model_primary = excluded.model_primary,
                       project_name = excluded.project_name,
                       scaffold = excluded.scaffold,
                       total_input_tokens = excluded.total_input_tokens,
                       total_output_tokens = excluded.total_output_tokens,
                       total_cache_read_tokens = excluded.total_cache_read_tokens,
                       total_cache_create_tokens = excluded.total_cache_create_tokens,
                       total_cost_usd = excluded.total_cost_usd,
                       message_count = excluded.message_count,
                       tool_call_count = excluded.tool_call_count,
                       source_member = excluded.source_member,
                       updated_at = excluded.updated_at""",
                (
                    sid,
                    sess.get("started_at"),
                    sess.get("ended_at"),
                    sess.get("model_primary"),
                    sess.get("project_name"),
                    sess.get("scaffold"),
                    sess.get("total_input_tokens", 0) if stats_config.get("tokens") else 0,
                    sess.get("total_output_tokens", 0) if stats_config.get("tokens") else 0,
                    sess.get("total_cache_read_tokens", 0) if stats_config.get("tokens") else 0,
                    sess.get("total_cache_create_tokens", 0) if stats_config.get("tokens") else 0,
                    sess.get("total_cost_usd", 0) if stats_config.get("cost") else 0,
                    sess.get("message_count", 0) if stats_config.get("messages") else 0,
                    sess.get("tool_call_count", 0) if stats_config.get("tool_calls") else 0,
                    member_name,
                    org_id,
                    now,
                ),
            )
            # Store uplift in uplift_outputs so it shows in the sessions table
            if stats_config.get("uplift") and sess.get("uplift_factor") is not None:
                db.execute(
                    """INSERT INTO uplift_outputs
                       (session_id, output_id, uplift_factor, metadata, timestamp)
                       VALUES (?, 'llm-judge', ?, '{"source": "remote"}', ?)
                       ON CONFLICT(session_id, output_id) DO UPDATE SET
                           uplift_factor = excluded.uplift_factor,
                           timestamp = excluded.timestamp""",
                    (sid, sess["uplift_factor"], now),
                )
            stored_count += 1

    return {
        "status": "ok",
        "org_name": data.get("org_name", ""),
        "sharing_config": new_sharing,
        "aggregate": data.get("aggregate"),
        "member_count": data.get("member_count", 0),
        "stored_sessions": stored_count,
    }


def sync_org(db: sqlite3.Connection, membership: dict) -> dict:
    """Push then pull for a single org."""
    push_result = push_org(db, membership)
    pull_result = pull_org(db, membership)
    return {
        "push": push_result,
        "pull": pull_result,
    }


def sync_all_orgs() -> list[dict]:
    """Sync all org memberships."""
    results = []
    with get_db() as db:
        memberships = db.execute("SELECT * FROM org_memberships").fetchall()
        for m in memberships:
            membership = dict(m)
            try:
                result = sync_org(db, membership)
                results.append({"org_id": membership["org_id"], **result})
            except Exception as e:
                logger.error("Sync failed for org %s: %s", membership["org_id"], e)
                results.append({"org_id": membership["org_id"], "error": str(e)})
    return results
