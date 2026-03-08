"""Session export to CSV/JSON formats."""

import csv
import io
import json
from datetime import datetime, timezone


def get_export_filename(fmt: str) -> str:
    """Return a default filename like sessions-YYYYMMDD.csv or .json."""
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"sessions-{date_str}.{fmt}"


def build_export_rows(
    db,
    session_ids: list[str] | None = None,
    *,
    include_transcript: bool = False,
    include_judge: bool = False,
    include_survey: bool = False,
    include_telemetry: bool = False,
    conditions: list[str] | None = None,
    params: list | None = None,
    limit: int = 0,
) -> list[dict]:
    """Assemble enriched session data for export.

    Either pass session_ids to export specific sessions, or conditions/params
    from _build_session_filters to export filtered sessions.
    """
    # Build the base query
    where_parts = list(conditions or [])
    query_params: list = list(params or [])

    if session_ids:
        placeholders = ",".join("?" * len(session_ids))
        where_parts.append(f"s.session_id IN ({placeholders})")
        query_params.extend(session_ids)

    where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
    limit_clause = f"LIMIT {limit}" if limit > 0 else ""

    # Core session query with uplift factors
    sql = f"""
        SELECT s.*,
            uo_judge.uplift_factor as uplift_llm_judge,
            uo_human.uplift_factor as uplift_human_est
        FROM sessions s
        LEFT JOIN uplift_outputs uo_judge
            ON s.session_id = uo_judge.session_id AND uo_judge.output_id = 'llm-judge'
        LEFT JOIN uplift_outputs uo_human
            ON s.session_id = uo_human.session_id AND uo_human.output_id = 'human-est'
        {where}
        ORDER BY s.started_at DESC
        {limit_clause}
    """
    rows = db.execute(sql, query_params).fetchall()
    rows = [dict(r) for r in rows]

    if not rows:
        return []

    sid_list = [r["session_id"] for r in rows]

    # Pre-fetch optional data in bulk
    survey_map = {}
    if include_survey:
        survey_map = _fetch_survey_data(db, sid_list)

    judge_map = {}
    if include_judge:
        judge_map = _fetch_judge_data(db, sid_list)

    transcript_map = {}
    if include_transcript:
        transcript_map = _fetch_transcript_data(db, sid_list)

    telemetry_map = {}
    if include_telemetry:
        telemetry_map = _fetch_telemetry_data(db, sid_list)

    # Assemble final rows
    result = []
    for row in rows:
        sid = row["session_id"]
        export_row = _core_columns(row)

        if include_survey:
            export_row.update(survey_map.get(sid, _empty_survey()))

        if include_judge:
            export_row.update(judge_map.get(sid, _empty_judge()))

        if include_transcript:
            export_row["compacted_transcript"] = transcript_map.get(sid, "")

        if include_telemetry:
            export_row["telemetry_messages"] = telemetry_map.get(sid, [])

        result.append(export_row)

    return result


def _core_columns(row: dict) -> dict:
    """Extract the always-included columns from a session row."""
    return {
        "session_id": row.get("session_id"),
        "project_name": row.get("project_name"),
        "project_path": row.get("project_path"),
        "git_branch": row.get("git_branch"),
        "scaffold": row.get("scaffold") or row.get("tool_source"),
        "started_at": row.get("started_at"),
        "ended_at": row.get("ended_at"),
        "model_primary": row.get("model_primary"),
        "message_count": row.get("message_count", 0),
        "tool_call_count": row.get("tool_call_count", 0),
        "total_input_tokens": row.get("total_input_tokens", 0),
        "total_output_tokens": row.get("total_output_tokens", 0),
        "total_cache_read_tokens": row.get("total_cache_read_tokens", 0),
        "total_cache_create_tokens": row.get("total_cache_create_tokens", 0),
        "total_cost_usd": row.get("total_cost_usd", 0.0),
        "is_local": row.get("is_local"),
        "continued_from": row.get("continued_from"),
        "continuation_type": row.get("continuation_type"),
        "uplift_llm_judge": row.get("uplift_llm_judge"),
        "uplift_human_est": row.get("uplift_human_est"),
    }


def _fetch_survey_data(db, session_ids: list[str]) -> dict[str, dict]:
    """Fetch survey responses, flattened."""
    if not session_ids:
        return {}
    placeholders = ",".join("?" * len(session_ids))
    rows = db.execute(
        f"SELECT session_id, answers, notes FROM survey_responses WHERE session_id IN ({placeholders})",
        session_ids,
    ).fetchall()
    result = {}
    for r in rows:
        answers = {}
        try:
            answers = json.loads(r["answers"]) if r["answers"] else {}
        except (json.JSONDecodeError, TypeError):
            pass
        result[r["session_id"]] = {
            "survey_human_est": answers.get("human-est"),
            "survey_notes": r["notes"] or "",
        }
    return result


def _empty_survey() -> dict:
    return {"survey_human_est": None, "survey_notes": ""}


def _fetch_judge_data(db, session_ids: list[str]) -> dict[str, dict]:
    """Fetch judge outputs (EAV), pivot to columns."""
    if not session_ids:
        return {}
    placeholders = ",".join("?" * len(session_ids))
    rows = db.execute(
        f"""SELECT session_id, field_name, value_text, value_numeric, value_type
            FROM judge_outputs WHERE session_id IN ({placeholders})""",
        session_ids,
    ).fetchall()

    # Group by session
    by_session: dict[str, dict] = {}
    for r in rows:
        sid = r["session_id"]
        if sid not in by_session:
            by_session[sid] = _empty_judge()
        field = r["field_name"]
        if field == "success":
            by_session[sid]["judge_success"] = r["value_text"]
        elif field == "confidence":
            by_session[sid]["judge_confidence"] = r["value_text"]
        elif field == "total_minutes_without_ai":
            by_session[sid]["judge_total_minutes_without_ai"] = r["value_numeric"]
        elif field == "reasoning":
            by_session[sid]["judge_reasoning"] = r["value_text"]
        elif field == "tasks":
            by_session[sid]["judge_tasks"] = r["value_text"]

    return by_session


def _empty_judge() -> dict:
    return {
        "judge_success": None,
        "judge_confidence": None,
        "judge_total_minutes_without_ai": None,
        "judge_reasoning": None,
        "judge_tasks": None,
    }


def _fetch_transcript_data(db, session_ids: list[str]) -> dict[str, str]:
    """Fetch compacted transcripts from script_results."""
    if not session_ids:
        return {}
    placeholders = ",".join("?" * len(session_ids))
    rows = db.execute(
        f"""SELECT session_id, result FROM script_results
            WHERE session_id IN ({placeholders})
            AND script_id = 'transcript-compact' AND status = 'completed'""",
        session_ids,
    ).fetchall()
    result = {}
    for r in rows:
        try:
            data = json.loads(r["result"]) if r["result"] else {}
            result[r["session_id"]] = data.get("compacted_transcript", "")
        except (json.JSONDecodeError, TypeError):
            pass
    return result


def _fetch_telemetry_data(db, session_ids: list[str]) -> dict[str, list[dict]]:
    """Fetch per-message telemetry."""
    if not session_ids:
        return {}
    placeholders = ",".join("?" * len(session_ids))
    rows = db.execute(
        f"""SELECT session_id, timestamp, role, model, input_tokens, output_tokens,
                   cache_read_tokens, cache_create_tokens, cost_usd, tool_names
            FROM messages WHERE session_id IN ({placeholders})
            ORDER BY timestamp""",
        session_ids,
    ).fetchall()
    result: dict[str, list[dict]] = {}
    for r in rows:
        sid = r["session_id"]
        if sid not in result:
            result[sid] = []
        result[sid].append({
            "timestamp": r["timestamp"],
            "role": r["role"],
            "model": r["model"],
            "input_tokens": r["input_tokens"],
            "output_tokens": r["output_tokens"],
            "cache_read_tokens": r["cache_read_tokens"],
            "cache_create_tokens": r["cache_create_tokens"],
            "cost_usd": r["cost_usd"],
            "tool_names": r["tool_names"],
        })
    return result


def format_csv(rows: list[dict]) -> str:
    """Format export rows as CSV string."""
    if not rows:
        return ""

    # Determine fieldnames from first row, ensuring consistent order
    fieldnames = list(rows[0].keys())

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        # JSON-serialize any list/dict values for CSV
        csv_row = {}
        for k, v in row.items():
            if isinstance(v, (list, dict)):
                csv_row[k] = json.dumps(v)
            else:
                csv_row[k] = v
        writer.writerow(csv_row)

    return output.getvalue()


def format_json(rows: list[dict]) -> str:
    """Format export rows as JSON string."""
    return json.dumps(rows, indent=2, default=str)
