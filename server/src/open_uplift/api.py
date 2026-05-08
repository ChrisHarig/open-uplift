import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from open_uplift.config import CUSTOM_TRANSCRIPTS_DIR, DASHBOARD_DIR, DEFAULT_SHARING_CONFIG
from open_uplift.db import get_db
from open_uplift.ingest import sync_all
from open_uplift.keystore import delete_api_key, list_api_keys, store_api_key
from open_uplift.llm_client import LLMClient
from open_uplift.job_queue import (
    _enqueue_unprocessed,
    _find_unprocessed_session_ids,
    _get_run_mode_config,
    _set_run_mode_config,
    cancel_job,
    enqueue_job,
    get_job,
    list_jobs,
    start_scheduler,
    start_worker,
    update_scheduler_config,
)
from open_uplift.scripts import get_script_results, run_script
from open_uplift.time_measurement import compute_concurrency_adjustment, compute_time_with_ai
from open_uplift.transcript import parse_transcript
from open_uplift.transcript_codex import parse_codex_transcript
from open_uplift.surveys import (
    _get_config,
    _set_config,
    add_question,
    add_survey,
    get_active_survey,
    get_active_survey_id,
    get_questions,
    get_surveys,
    set_active_survey,
    slugify,
    submit_survey_response,
)


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)

    # --- API routes ---

    @app.route("/api/health")
    def health():
        """Health check endpoint.

        Returns: {"status": "ok"}
        """
        return jsonify({"status": "ok"})

    @app.route("/api/setup/state")
    def setup_state():
        """Check onboarding state: sessions, profile, keys, scaffolds, orgs.

        Returns: {has_sessions, has_profile, has_api_keys, has_scaffolds, has_organizations, welcome_dismissed}
        """
        with get_db() as db:
            has_sessions = db.execute("SELECT COUNT(*) as c FROM sessions").fetchone()["c"] > 0
            has_profile = _get_config(db, "user_profile") is not None
            has_api_keys = db.execute("SELECT COUNT(*) as c FROM api_keys").fetchone()["c"] > 0
            has_scaffolds = db.execute("SELECT COUNT(*) as c FROM scaffolds").fetchone()["c"] > 0
            has_organizations = db.execute("SELECT COUNT(*) as c FROM organizations").fetchone()["c"] > 0
            welcome_dismissed = _get_config(db, "welcome_dismissed") is True
        return jsonify({
            "has_sessions": has_sessions,
            "has_profile": has_profile,
            "has_api_keys": has_api_keys,
            "has_scaffolds": has_scaffolds,
            "has_organizations": has_organizations,
            "welcome_dismissed": welcome_dismissed,
        })

    @app.route("/api/setup/dismiss-welcome", methods=["POST"])
    def dismiss_welcome():
        """Dismiss the welcome banner permanently.

        Returns: {"status": "ok"}
        """
        with get_db() as db:
            _set_config(db, "welcome_dismissed", True)
        return jsonify({"status": "ok"})

    @app.route("/api/overview")
    def overview():
        """Dashboard overview stats over a date range.

        Query: days (int, default 30)
        Returns: {totals, daily, self_reports}
        """
        days = request.args.get("days", "30", type=str)
        with get_db() as db:
            totals = db.execute(
                """SELECT
                     COUNT(*) as total_sessions,
                     COALESCE(SUM(total_input_tokens + total_output_tokens), 0) as total_tokens,
                     COALESCE(SUM(message_count), 0) as total_messages,
                     COALESCE(SUM(tool_call_count), 0) as total_tool_calls
                   FROM sessions
                   WHERE started_at >= datetime('now', ?)""",
                (f"-{days} days",),
            ).fetchone()

            daily = db.execute(
                """SELECT
                     date(started_at) as day,
                     COUNT(*) as sessions,
                     COALESCE(SUM(total_input_tokens + total_output_tokens), 0) as tokens
                   FROM sessions
                   WHERE started_at >= datetime('now', ?)
                   GROUP BY date(started_at)
                   ORDER BY day""",
                (f"-{days} days",),
            ).fetchall()

            report_stats = db.execute(
                """SELECT
                     ROUND(COALESCE(AVG(uo.uplift_factor), 0), 2) as avg_speedup_factor,
                     COUNT(*) as total_reports
                   FROM uplift_outputs uo"""
            ).fetchone()

        return jsonify({
            "totals": dict(totals),
            "daily": [dict(r) for r in daily],
            "self_reports": dict(report_stats),
        })

    @app.route("/api/projects")
    def projects_list():
        """List all projects with session counts and token usage.

        Query: org_id (optional, filter by organization)
        Returns: [{project_name, project_path, session_count, total_tokens, ...}]
        """
        org_id = request.args.get("org_id", None, type=str)
        with get_db() as db:
            org_filter = ""
            org_params: list = []
            if org_id:
                cond, org_params = _org_folder_filter(db, org_id)
                if cond is None:
                    return jsonify([])
                org_filter = f" AND {cond}"

            rows = db.execute(
                f"""SELECT
                     s.project_name,
                     s.project_path,
                     COUNT(*) as session_count,
                     COALESCE(SUM(s.total_input_tokens + s.total_output_tokens), 0) as total_tokens,
                     COALESCE(SUM(s.message_count), 0) as total_messages,
                     COALESCE(SUM(s.tool_call_count), 0) as total_tool_calls,
                     MAX(s.started_at) as last_active,
                     o.org_id,
                     o.name as org_name,
                     o.is_verified as org_is_verified,
                     o.org_mode as org_mode
                   FROM sessions s
                   LEFT JOIN org_folders of2 ON (
                     s.project_path = of2.folder_path
                     OR s.project_path LIKE of2.folder_path || '/%'
                   )
                   LEFT JOIN organizations o ON of2.org_id = o.org_id
                   WHERE s.project_name IS NOT NULL{org_filter}
                   GROUP BY s.project_name
                   ORDER BY last_active DESC""",
                org_params,
            ).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.route("/api/projects/stats")
    def project_stats():
        """Aggregate stats for a single project path.

        Query: project_path (required)
        Returns: {session_count, total_tokens, total_messages, total_tool_calls, last_active}
        """
        project_path = request.args.get("project_path", None, type=str)
        if not project_path:
            return jsonify({"error": "project_path required"}), 400
        with get_db() as db:
            row = db.execute(
                """SELECT
                     COUNT(*) as session_count,
                     COALESCE(SUM(total_input_tokens + total_output_tokens), 0) as total_tokens,
                     COALESCE(SUM(message_count), 0) as total_messages,
                     COALESCE(SUM(tool_call_count), 0) as total_tool_calls,
                     MAX(started_at) as last_active
                   FROM sessions
                   WHERE project_path = ? OR project_path LIKE ? || '/%'""",
                (project_path, project_path),
            ).fetchone()
        return jsonify(dict(row))

    def _build_session_filters(db, *, project=None, project_path=None, subfolders=False,
                               date_from=None, date_to=None, model=None, scaffold=None,
                               has_survey=None, has_judge=None, has_compaction=None,
                               judge_success=None, is_local=None, org_id=None,
                               source_member=None):
        """Build SQL WHERE conditions and params for session queries.

        Returns (conditions: list[str], params: list) or None if org has no folders
        (caller should return empty results).
        """
        conditions = []
        params: list = []

        # org_id filter
        if org_id == "personal":
            conditions.append(
                "NOT EXISTS (SELECT 1 FROM org_folders of2"
                " WHERE s.project_path = of2.folder_path"
                " OR s.project_path LIKE of2.folder_path || '/%')"
            )
        elif org_id == "local":
            conditions.append("s.is_local = 1")
        elif org_id:
            cond, org_params = _org_folder_filter(db, org_id)
            if cond is None:
                return None
            conditions.append(cond)
            params.extend(org_params)

        if project_path and subfolders:
            conditions.append("(s.project_path = ? OR s.project_path LIKE ? || '/%')")
            params.extend([project_path, project_path])
        elif project:
            conditions.append("s.project_name = ?")
            params.append(project)

        if date_from:
            conditions.append("date(s.started_at) >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("date(s.started_at) <= ?")
            params.append(date_to)
        if model:
            conditions.append("s.model_primary = ?")
            params.append(model)
        if scaffold:
            conditions.append("COALESCE(s.scaffold, s.tool_source) = ?")
            params.append(scaffold)

        # has_survey filter
        if has_survey == "true":
            conditions.append("EXISTS (SELECT 1 FROM survey_responses WHERE session_id = s.session_id)")
        elif has_survey == "false":
            conditions.append("NOT EXISTS (SELECT 1 FROM survey_responses WHERE session_id = s.session_id)")

        # has_judge filter
        if has_judge == "true":
            conditions.append("EXISTS (SELECT 1 FROM script_results WHERE session_id = s.session_id AND script_id = 'llm-time-estimate' AND status = 'completed')")
        elif has_judge == "false":
            conditions.append("NOT EXISTS (SELECT 1 FROM script_results WHERE session_id = s.session_id AND script_id = 'llm-time-estimate' AND status = 'completed')")

        # has_compaction filter
        if has_compaction == "true":
            conditions.append("EXISTS (SELECT 1 FROM script_results WHERE session_id = s.session_id AND script_id = 'transcript-compact' AND status = 'completed')")
        elif has_compaction == "false":
            conditions.append("NOT EXISTS (SELECT 1 FROM script_results WHERE session_id = s.session_id AND script_id = 'transcript-compact' AND status = 'completed')")

        # judge_success filter
        if judge_success == "true":
            conditions.append("EXISTS (SELECT 1 FROM judge_outputs WHERE session_id = s.session_id AND field_name = 'success' AND value_text = 'true')")
        elif judge_success == "false":
            conditions.append("EXISTS (SELECT 1 FROM judge_outputs WHERE session_id = s.session_id AND field_name = 'success' AND value_text = 'false')")

        # is_local filter
        if is_local == "true":
            conditions.append("COALESCE(s.is_local, 1) = 1")
        elif is_local == "false":
            conditions.append("COALESCE(s.is_local, 1) = 0")

        # source_member filter (for hub-stored sessions from specific member)
        if source_member:
            conditions.append("s.source_member = ?")
            params.append(source_member)

        return conditions, params

    @app.route("/api/sessions")
    def sessions_list():
        """List sessions with filtering, pagination, and enrichment.

        Query: limit, offset, project, project_path, date_from, date_to, model, scaffold,
               has_survey, has_judge, has_compaction, judge_success, is_local, org_id, source_member
        Returns: {sessions, total}
        """
        limit = request.args.get("limit", 50, type=int)
        offset = request.args.get("offset", 0, type=int)

        with get_db() as db:
            result = _build_session_filters(
                db,
                project=request.args.get("project", None, type=str),
                project_path=request.args.get("project_path", None, type=str),
                subfolders=request.args.get("subfolders", "", type=str).lower() == "true",
                date_from=request.args.get("date_from", None, type=str),
                date_to=request.args.get("date_to", None, type=str),
                model=request.args.get("model", None, type=str),
                scaffold=request.args.get("scaffold", None, type=str),
                has_survey=request.args.get("has_survey", None, type=str),
                has_judge=request.args.get("has_judge", None, type=str),
                has_compaction=request.args.get("has_compaction", None, type=str),
                judge_success=request.args.get("judge_success", None, type=str),
                is_local=request.args.get("is_local", None, type=str),
                org_id=request.args.get("org_id", None, type=str),
                source_member=request.args.get("source_member", None, type=str),
            )
            if result is None:
                return jsonify({"sessions": [], "total": 0})
            conditions, params = result

            where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
            report_join = ""
            report_col = "EXISTS (SELECT 1 FROM survey_responses WHERE session_id = s.session_id) as has_report"
            # Staleness: a script result is "current" if completed and message_count matches
            compact_current = (
                "CASE WHEN EXISTS ("
                "  SELECT 1 FROM script_results sc"
                "  WHERE sc.session_id = s.session_id"
                "    AND sc.script_id = 'transcript-compact'"
                "    AND sc.status = 'completed'"
                "    AND sc.session_message_count >= s.message_count"
                ") THEN 1 ELSE 0 END as compaction_current"
            )
            judge_current = (
                "CASE WHEN EXISTS ("
                "  SELECT 1 FROM script_results sj"
                "  WHERE sj.session_id = s.session_id"
                "    AND sj.script_id = 'llm-time-estimate'"
                "    AND sj.status = 'completed'"
                "    AND sj.session_message_count >= s.message_count"
                ") THEN 1 ELSE 0 END as judge_current"
            )
            judge_success_col = (
                "(SELECT jo.value_text FROM judge_outputs jo"
                " WHERE jo.session_id = s.session_id AND jo.field_name = 'success'"
                ") as judge_success"
            )

            org_col = "o.name as org_name"
            org_join = (
                "LEFT JOIN ("
                "  SELECT of2.org_id, of2.folder_path FROM org_folders of2"
                ") of_match ON ("
                "  s.project_path = of_match.folder_path"
                "  OR s.project_path LIKE of_match.folder_path || '/%'"
                ")"
                " LEFT JOIN organizations o ON of_match.org_id = o.org_id"
            )
            # GROUP BY to avoid duplicates when a session matches multiple org_folders
            group_by = "GROUP BY s.session_id"

            rows = db.execute(
                f"""SELECT s.*, {report_col}, {compact_current}, {judge_current}, {judge_success_col}, {org_col}
                   FROM sessions s {org_join} {report_join}
                   {where}
                   {group_by}
                   ORDER BY s.started_at DESC
                   LIMIT ? OFFSET ?""",
                (*params, limit, offset),
            ).fetchall()
            count = db.execute(
                f"SELECT COUNT(DISTINCT s.session_id) as c FROM sessions s {where}",
                params,
            ).fetchone()

        return jsonify({
            "sessions": [dict(r) for r in rows],
            "total": count["c"],
        })

    @app.route("/api/sessions/export")
    def sessions_export():
        """Export sessions as CSV or JSON file download."""
        from open_uplift.cli.export import build_export_rows, format_csv, format_json, get_export_filename

        fmt = request.args.get("format", "csv", type=str)
        if fmt not in ("csv", "json"):
            return jsonify({"error": "format must be csv or json"}), 400

        session_ids_param = request.args.get("session_ids", None, type=str)
        session_ids = [s.strip() for s in session_ids_param.split(",") if s.strip()] if session_ids_param else None

        include_transcript = request.args.get("include_transcript", "false").lower() == "true"
        include_judge = request.args.get("include_judge", "false").lower() == "true"
        include_survey = request.args.get("include_survey", "false").lower() == "true"
        include_telemetry = request.args.get("include_telemetry", "false").lower() == "true"

        with get_db() as db:
            conditions = None
            params = None
            if not session_ids:
                result = _build_session_filters(
                    db,
                    project=request.args.get("project", None, type=str),
                    project_path=request.args.get("project_path", None, type=str),
                    subfolders=request.args.get("subfolders", "", type=str).lower() == "true",
                    date_from=request.args.get("date_from", None, type=str),
                    date_to=request.args.get("date_to", None, type=str),
                    model=request.args.get("model", None, type=str),
                    scaffold=request.args.get("scaffold", None, type=str),
                    has_survey=request.args.get("has_survey", None, type=str),
                    has_judge=request.args.get("has_judge", None, type=str),
                    has_compaction=request.args.get("has_compaction", None, type=str),
                    judge_success=request.args.get("judge_success", None, type=str),
                    is_local=request.args.get("is_local", None, type=str),
                    org_id=request.args.get("org_id", None, type=str),
                    source_member=request.args.get("source_member", None, type=str),
                )
                if result is None:
                    # Org with no folders
                    if fmt == "csv":
                        return app.response_class("", mimetype="text/csv")
                    return jsonify([])
                conditions, params = result

            rows = build_export_rows(
                db,
                session_ids=session_ids,
                include_transcript=include_transcript,
                include_judge=include_judge,
                include_survey=include_survey,
                include_telemetry=include_telemetry,
                conditions=conditions,
                params=params,
            )

        filename = get_export_filename(fmt)
        if fmt == "csv":
            output = format_csv(rows)
            response = app.response_class(output, mimetype="text/csv")
        else:
            output = format_json(rows)
            response = app.response_class(output, mimetype="application/json")

        response.headers["Content-Disposition"] = f"attachment; filename={filename}"
        return response

    @app.route("/api/sessions/filter-options")
    def session_filter_options():
        """Return distinct values for filter dropdowns."""
        org_id = request.args.get("org_id", None, type=str)
        with get_db() as db:
            org_where = ""
            org_params: list = []
            if org_id == "personal":
                org_where = (
                    " AND NOT EXISTS (SELECT 1 FROM org_folders of2"
                    " WHERE s.project_path = of2.folder_path"
                    " OR s.project_path LIKE of2.folder_path || '/%')"
                )
            elif org_id:
                cond, org_params = _org_folder_filter(db, org_id)
                if cond is None:
                    return jsonify({"models": [], "scaffolds": [], "projects": []})
                org_where = f" AND {cond}"

            models = db.execute(
                f"SELECT DISTINCT s.model_primary FROM sessions s WHERE s.model_primary IS NOT NULL{org_where} ORDER BY s.model_primary",
                org_params,
            ).fetchall()
            scaffolds = db.execute(
                f"SELECT DISTINCT COALESCE(s.scaffold, s.tool_source) as scaffold FROM sessions s WHERE 1=1{org_where} ORDER BY scaffold",
                org_params,
            ).fetchall()
            projects = db.execute(
                f"SELECT DISTINCT s.project_name FROM sessions s WHERE s.project_name IS NOT NULL{org_where} ORDER BY s.project_name",
                org_params,
            ).fetchall()
        return jsonify({
            "models": [r["model_primary"] for r in models],
            "scaffolds": [r["scaffold"] for r in scaffolds],
            "projects": [r["project_name"] for r in projects],
        })

    @app.route("/api/sessions/<session_id>")
    def session_detail(session_id):
        """Get session metadata and all messages for a single session.

        Returns: {session, messages}
        """
        with get_db() as db:
            session = db.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if not session:
                return jsonify({"error": "not found"}), 404
            messages = db.execute(
                """SELECT * FROM messages
                   WHERE session_id = ?
                   ORDER BY timestamp""",
                (session_id,),
            ).fetchall()
        return jsonify({
            "session": dict(session),
            "messages": [dict(m) for m in messages],
        })

    @app.route("/api/sessions/<session_id>/transcript")
    def session_transcript(session_id):
        """Parse and return the raw transcript for a session.

        Returns: parsed transcript data (format depends on tool_source)
        """
        with get_db() as db:
            # Try exact match first (Claude Code: {uuid}.jsonl)
            row = db.execute(
                "SELECT file_path FROM ingest_log WHERE file_path LIKE ?",
                (f"%/{session_id}.jsonl",),
            ).fetchone()
            # Try partial match for Codex rollout files (rollout-*-{uuid}.jsonl)
            if not row:
                row = db.execute(
                    "SELECT file_path FROM ingest_log WHERE file_path LIKE ?",
                    (f"%-{session_id}.jsonl",),
                ).fetchone()
            # Also look up the scaffold to pick the right parser
            session_row = db.execute(
                "SELECT tool_source FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if not row:
            return jsonify({"error": "session not found"}), 404
        path = Path(row["file_path"])
        if not path.is_file():
            return jsonify({"error": "transcript file not found on disk"}), 404
        tool_source = session_row["tool_source"] if session_row else "claude_code"
        if tool_source == "codex":
            data = parse_codex_transcript(path)
        else:
            data = parse_transcript(path)
        return jsonify(data)

    def _session_path_filter(project_path, subfolders):
        """Return (join_clause, where_clause, params) for filtering messages by project path."""
        if project_path and subfolders:
            return (
                "JOIN sessions s ON m.session_id = s.session_id",
                "AND (s.project_path = ? OR s.project_path LIKE ? || '/%')",
                (project_path, project_path),
            )
        elif project_path:
            return (
                "JOIN sessions s ON m.session_id = s.session_id",
                "AND s.project_path = ?",
                (project_path,),
            )
        return ("", "", ())

    @app.route("/api/tokens/by-model")
    def tokens_by_model():
        """Token usage breakdown by model.

        Query: project_path (optional), subfolders (bool)
        Returns: [{model, tokens}]
        """
        project_path = request.args.get("project_path", None, type=str)
        subfolders = request.args.get("subfolders", "", type=str).lower() == "true"
        join, where, params = _session_path_filter(project_path, subfolders)
        with get_db() as db:
            rows = db.execute(
                f"""SELECT
                     model,
                     COALESCE(SUM(input_tokens + output_tokens), 0) as tokens
                   FROM messages m
                   {join}
                   WHERE model IS NOT NULL {where}
                   GROUP BY model
                   ORDER BY tokens DESC""",
                params,
            ).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.route("/api/tokens/by-source")
    def tokens_by_source():
        """Token usage breakdown by tool source (scaffold).

        Query: project_path (optional), subfolders (bool)
        Returns: [{tool_source, tokens}]
        """
        project_path = request.args.get("project_path", None, type=str)
        subfolders = request.args.get("subfolders", "", type=str).lower() == "true"
        with get_db() as db:
            if project_path and subfolders:
                path_where = "AND (s.project_path = ? OR s.project_path LIKE ? || '/%')"
                params = (project_path, project_path)
            elif project_path:
                path_where = "AND s.project_path = ?"
                params = (project_path,)
            else:
                path_where = ""
                params = ()
            rows = db.execute(
                f"""SELECT
                     s.tool_source,
                     COALESCE(SUM(m.input_tokens + m.output_tokens), 0) as tokens
                   FROM messages m
                   JOIN sessions s ON m.session_id = s.session_id
                   WHERE m.model IS NOT NULL {path_where}
                   GROUP BY s.tool_source
                   ORDER BY tokens DESC""",
                params,
            ).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.route("/api/tokens/timeseries")
    def tokens_timeseries():
        """Daily token usage timeseries (input, output, cache).

        Query: days (default 30), project_path (optional), subfolders (bool)
        Returns: [{day, input_tokens, output_tokens, cache_read, cache_create}]
        """
        days = request.args.get("days", "30", type=str)
        project_path = request.args.get("project_path", None, type=str)
        subfolders = request.args.get("subfolders", "", type=str).lower() == "true"
        join, where, params = _session_path_filter(project_path, subfolders)
        with get_db() as db:
            rows = db.execute(
                f"""SELECT
                     date(timestamp) as day,
                     COALESCE(SUM(input_tokens), 0) as input_tokens,
                     COALESCE(SUM(output_tokens), 0) as output_tokens,
                     COALESCE(SUM(cache_read_tokens), 0) as cache_read,
                     COALESCE(SUM(cache_create_tokens), 0) as cache_create
                   FROM messages m
                   {join}
                   WHERE timestamp >= datetime('now', ?)
                     AND role = 'assistant' {where}
                   GROUP BY date(timestamp)
                   ORDER BY day""",
                (f"-{days} days", *params),
            ).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.route("/api/tools/usage")
    def tools_usage():
        """Aggregate tool call counts across all sessions.

        Returns: [{tool, count}] sorted by count descending
        """
        with get_db() as db:
            rows = db.execute(
                """SELECT tool_names FROM messages
                   WHERE tool_names IS NOT NULL AND tool_names != ''"""
            ).fetchall()
        counter: dict[str, int] = {}
        for row in rows:
            for name in row["tool_names"].split(","):
                name = name.strip()
                if name:
                    counter[name] = counter.get(name, 0) + 1
        sorted_tools = sorted(counter.items(), key=lambda x: x[1], reverse=True)
        return jsonify([{"tool": t, "count": c} for t, c in sorted_tools])

    # --- Surveys, questions, responses, outputs ---

    @app.route("/api/questions")
    def questions_list():
        """List all defined survey questions.

        Returns: {question_id: {label, type, ...}}
        """
        with get_db() as db:
            return jsonify(get_questions(db))

    @app.route("/api/questions", methods=["POST"])
    def create_question():
        """Create a new survey question.

        Body: {label, type, description?, suffix?, placeholder?, required?, min?, max?}
        Returns: updated questions map (201)
        """
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON body required"}), 400
        for field in ("label", "type"):
            if not data.get(field):
                return jsonify({"error": f"{field} is required"}), 400
        qid = slugify(data["label"])
        if not qid:
            return jsonify({"error": "label must contain at least one alphanumeric character"}), 400
        with get_db() as db:
            existing = get_questions(db)
            if qid in existing:
                return jsonify({"error": f"A question named '{data['label']}' already exists"}), 409
            # Also check for duplicate labels on existing questions
            for q in existing.values():
                if q.get("label", "").strip().lower() == data["label"].strip().lower():
                    return jsonify({"error": f"A question named '{data['label']}' already exists"}), 409
            question = {
                "id": qid,
                "label": data["label"],
                "description": data.get("description", ""),
                "type": data["type"],
                "suffix": data.get("suffix", ""),
                "placeholder": data.get("placeholder", ""),
                "required": data.get("required", True),
            }
            if data["type"] == "number":
                validation: dict = {"type": "number"}
                if "min" in data:
                    validation["min"] = data["min"]
                if "max" in data:
                    validation["max"] = data["max"]
                question["validation"] = validation
            add_question(db, question)
            return jsonify(get_questions(db)), 201

    @app.route("/api/surveys")
    def surveys_list():
        """List all surveys and identify the active one.

        Returns: {surveys, active}
        """
        with get_db() as db:
            surveys = get_surveys(db)
            active_id = get_active_survey_id(db)
        return jsonify({"surveys": surveys, "active": active_id})

    @app.route("/api/surveys", methods=["POST"])
    def create_survey():
        """Create a new survey with a set of question IDs.

        Body: {name, questions, description?}
        Returns: {surveys, active} (201)
        """
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON body required"}), 400
        for field in ("name", "questions"):
            if not data.get(field):
                return jsonify({"error": f"{field} is required"}), 400
        sid = slugify(data["name"])
        if not sid:
            return jsonify({"error": "name must contain at least one alphanumeric character"}), 400
        with get_db() as db:
            existing_surveys = get_surveys(db)
            if sid in existing_surveys:
                return jsonify({"error": f"A survey named '{data['name']}' already exists"}), 409
            # Also check for duplicate names on existing surveys
            for s in existing_surveys.values():
                if s.get("name", "").strip().lower() == data["name"].strip().lower():
                    return jsonify({"error": f"A survey named '{data['name']}' already exists"}), 409
            existing_questions = get_questions(db)
            for qid in data["questions"]:
                if qid not in existing_questions:
                    return jsonify({"error": f"Question '{qid}' not found"}), 400
            survey = {
                "id": sid,
                "name": data["name"],
                "description": data.get("description", ""),
                "questions": data["questions"],
                "scripts": [],
                "outputs": [],
            }
            add_survey(db, survey)
            surveys = get_surveys(db)
            active_id = get_active_survey_id(db)
        return jsonify({"surveys": surveys, "active": active_id}), 201

    @app.route("/api/surveys/<survey_id>", methods=["PUT"])
    def update_survey(survey_id):
        """Update a survey's name, description, or question list.

        Body: {name?, description?, questions?}
        Returns: {surveys, active}
        """
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON body required"}), 400
        with get_db() as db:
            existing_surveys = get_surveys(db)
            if survey_id not in existing_surveys:
                return jsonify({"error": f"Survey '{survey_id}' not found"}), 404
            survey = existing_surveys[survey_id]
            if "questions" in data:
                existing_questions = get_questions(db)
                for qid in data["questions"]:
                    if qid not in existing_questions:
                        return jsonify({"error": f"Question '{qid}' not found"}), 400
                survey["questions"] = data["questions"]
            if "name" in data:
                survey["name"] = data["name"]
            if "description" in data:
                survey["description"] = data["description"]
            add_survey(db, survey)
            surveys = get_surveys(db)
            active_id = get_active_survey_id(db)
        return jsonify({"surveys": surveys, "active": active_id})

    @app.route("/api/surveys/<survey_id>", methods=["DELETE"])
    def delete_survey(survey_id):
        """Delete a survey (cannot delete the active survey).

        Returns: {surveys, active}
        """
        with get_db() as db:
            existing_surveys = get_surveys(db)
            if survey_id not in existing_surveys:
                return jsonify({"error": f"Survey '{survey_id}' not found"}), 404
            active_id = get_active_survey_id(db)
            if survey_id == active_id:
                return jsonify({"error": "Cannot delete the active survey. Set a different survey as active first."}), 400
            del existing_surveys[survey_id]
            _set_config(db, "surveys", existing_surveys)
            surveys = get_surveys(db)
            active_id = get_active_survey_id(db)
        return jsonify({"surveys": surveys, "active": active_id})

    @app.route("/api/surveys/active")
    def active_survey():
        """Get the currently active survey definition.

        Returns: {survey}
        """
        with get_db() as db:
            survey = get_active_survey(db)
        return jsonify({"survey": survey})

    @app.route("/api/surveys/active", methods=["PUT"])
    def set_active():
        """Set which survey is active.

        Body: {survey_id}
        Returns: {active}
        """
        data = request.get_json()
        if not data or "survey_id" not in data:
            return jsonify({"error": "survey_id required"}), 400
        try:
            with get_db() as db:
                set_active_survey(db, data["survey_id"])
        except ValueError as e:
            return jsonify({"error": str(e)}), 404
        return jsonify({"active": data["survey_id"]})

    @app.route("/api/survey-responses")
    def survey_responses_list():
        """List all survey responses with answers and computed outputs.

        Returns: [{id, session_id, answers, outputs, ...}]
        """
        with get_db() as db:
            rows = db.execute(
                """SELECT sr.*, s.project_name
                   FROM survey_responses sr
                   LEFT JOIN sessions s ON sr.session_id = s.session_id
                   ORDER BY sr.timestamp DESC"""
            ).fetchall()
            # Attach outputs to each response
            results = []
            for r in rows:
                d = dict(r)
                d["answers"] = json.loads(d["answers"])
                outputs = db.execute(
                    "SELECT output_id, uplift_factor, metadata FROM uplift_outputs WHERE survey_response_id = ?",
                    (d["id"],),
                ).fetchall()
                d["outputs"] = [dict(o) for o in outputs]
                results.append(d)
        return jsonify(results)

    @app.route("/api/survey-responses", methods=["POST"])
    def create_survey_response():
        """Submit a survey response for a session.

        Body: {session_id, survey_id, answers, notes?}
        Returns: {id, session_id, outputs} (201)
        """
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON body required"}), 400
        session_id = data.get("session_id")
        survey_id = data.get("survey_id")
        answers = data.get("answers", {})
        notes = data.get("notes", "")
        if not session_id or not survey_id:
            return jsonify({"error": "session_id and survey_id required"}), 400
        try:
            with get_db() as db:
                response_id, outputs = submit_survey_response(
                    db, session_id, survey_id, answers, notes
                )
        except ValueError as e:
            return jsonify({"error": str(e)}), 409

        return jsonify({
            "id": response_id,
            "session_id": session_id,
            "outputs": outputs,
        }), 201

    @app.route("/api/uplift-outputs/summary")
    def uplift_summary():
        """Aggregated uplift output stats, filtered to successful sessions.

        Query: org_id (optional)
        Returns: {total_responses, total_measured_sessions, outputs}
        """
        org_id = request.args.get("org_id")
        with get_db() as db:
            org_clause = ""
            org_params: list = []
            if org_id:
                cond, org_params = _org_folder_filter(db, org_id)
                if cond is None:
                    return jsonify({"total_responses": 0, "total_measured_sessions": 0, "outputs": []})
                org_clause = f" AND {cond}"

            rows = db.execute(
                f"""SELECT
                     uo.output_id,
                     COUNT(DISTINCT uo.session_id) as count,
                     ROUND(COALESCE(AVG(uo.uplift_factor), 0), 2) as avg_uplift
                   FROM uplift_outputs uo
                   JOIN sessions s ON s.session_id = uo.session_id
                   LEFT JOIN judge_outputs jo ON jo.session_id = uo.session_id AND jo.field_name = 'success'
                   WHERE uo.session_id IS NOT NULL
                     AND (jo.id IS NULL OR jo.value_text = 'true')
                     {org_clause}
                   GROUP BY uo.output_id""",
                org_params,
            ).fetchall()
            total_survey = db.execute("SELECT COUNT(*) as c FROM survey_responses").fetchone()
            total_measured = db.execute(
                f"""SELECT COUNT(DISTINCT uo.session_id) as c
                   FROM uplift_outputs uo
                   JOIN sessions s ON s.session_id = uo.session_id
                   WHERE uo.session_id IS NOT NULL{org_clause}""",
                org_params,
            ).fetchone()
        return jsonify({
            "total_responses": total_survey["c"],
            "total_measured_sessions": total_measured["c"],
            "outputs": [dict(r) for r in rows],
        })

    @app.route("/api/uplift-outputs/by-session")
    def uplift_by_session():
        """Map of session_id to {output_id: uplift_factor} for all sessions.

        Returns: {session_id: {output_id: uplift_factor}}
        """
        with get_db() as db:
            rows = db.execute(
                "SELECT session_id, output_id, uplift_factor FROM uplift_outputs WHERE session_id IS NOT NULL"
            ).fetchall()
        result: dict[str, dict[str, float]] = {}
        for r in rows:
            sid = r["session_id"]
            if sid not in result:
                result[sid] = {}
            result[sid][r["output_id"]] = r["uplift_factor"]
        return jsonify(result)

    @app.route("/api/sessions/<session_id>/uplift-outputs")
    def session_uplift_outputs(session_id: str):
        """Get uplift outputs for a specific session.

        Returns: [{output_id, uplift_factor, metadata, timestamp}]
        """
        with get_db() as db:
            rows = db.execute(
                """SELECT output_id, uplift_factor, metadata, timestamp
                   FROM uplift_outputs
                   WHERE session_id = ?""",
                (session_id,),
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["metadata"] = json.loads(d["metadata"]) if d["metadata"] else {}
            except (json.JSONDecodeError, TypeError):
                d["metadata"] = {}
            result.append(d)
        return jsonify(result)

    # --- Legacy self-reports (backward compat) ---

    @app.route("/api/self-reports")
    def self_reports():
        """List legacy self-reports (backward compat).

        Returns: [{session_id, project_name, ...}]
        """
        with get_db() as db:
            rows = db.execute(
                """SELECT sr.*, s.project_name
                   FROM self_reports sr
                   LEFT JOIN sessions s ON sr.session_id = s.session_id
                   ORDER BY sr.timestamp DESC"""
            ).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.route("/api/self-reports", methods=["POST"])
    def create_self_report():
        """Backward-compatible endpoint: delegates to survey response system."""
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON body required"}), 400
        session_id = data.get("session_id")
        speedup_factor = data.get("speedup_factor")
        notes = data.get("notes", "")
        if not session_id or speedup_factor is None:
            return jsonify({"error": "session_id and speedup_factor required"}), 400
        try:
            speedup_factor = float(speedup_factor)
            if not (0.1 <= speedup_factor <= 100.0):
                raise ValueError()
        except (ValueError, TypeError):
            return jsonify({"error": "speedup_factor must be a number between 0.1 and 100"}), 422
        try:
            with get_db() as db:
                response_id, outputs = submit_survey_response(
                    db, session_id, "survey-1",
                    {"human-est": speedup_factor}, notes,
                )
        except ValueError as e:
            return jsonify({"error": str(e)}), 409
        return jsonify({"id": response_id, "session_id": session_id}), 201

    @app.route("/api/self-reports/summary")
    def self_reports_summary():
        """Legacy summary of all uplift outputs.

        Returns: {summary: {total, avg_speedup_factor}}
        """
        with get_db() as db:
            summary = db.execute(
                """SELECT
                     COUNT(*) as total,
                     ROUND(COALESCE(AVG(uplift_factor), 0), 2) as avg_speedup_factor
                   FROM uplift_outputs"""
            ).fetchone()

        return jsonify({
            "summary": dict(summary),
        })

    @app.route("/api/sync", methods=["POST"])
    def api_sync():
        """Trigger a full ingest sync of transcript files.

        Returns: {new_files, updated_files, ...}
        """
        stats = sync_all()
        return jsonify(stats)

    @app.route("/api/sync/status")
    def sync_status():
        """Get the timestamp of the last ingest sync.

        Returns: {last_synced}
        """
        with get_db() as db:
            row = db.execute(
                "SELECT MAX(last_synced) as last_synced FROM ingest_log"
            ).fetchone()
        return jsonify({
            "last_synced": row["last_synced"] if row else None,
        })

    # --- API Keys (Phase 1) ---

    @app.route("/api/api-keys")
    def api_keys_list():
        """List stored API keys (and env-var keys) with masked values.

        Returns: [{provider, key_name, source, ...}]
        """
        from open_uplift.keystore import PROVIDER_ENV_VARS
        with get_db() as db:
            keys = list_api_keys(db)
        # Include env var keys that aren't already stored
        stored_providers = {k["provider"] for k in keys}
        for provider, env_var in PROVIDER_ENV_VARS.items():
            if provider not in stored_providers and os.environ.get(env_var):
                keys.append({
                    "provider": provider,
                    "key_name": "env",
                    "source": "env",
                    "created_at": None,
                    "last_used_at": None,
                })
        return jsonify(keys)

    @app.route("/api/api-keys", methods=["POST"])
    def api_keys_add():
        """Store a new API key for a provider.

        Body: {provider, api_key, key_name?}
        Returns: {status, provider, key_name} (201)
        """
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON body required"}), 400
        provider = data.get("provider")
        key_name = data.get("key_name", "default")
        api_key_val = data.get("api_key")
        if not provider or not api_key_val:
            return jsonify({"error": "provider and api_key required"}), 400
        with get_db() as db:
            store_api_key(db, provider, key_name, api_key_val)
        return jsonify({"status": "stored", "provider": provider, "key_name": key_name}), 201

    @app.route("/api/api-keys/<provider>/<key_name>", methods=["DELETE"])
    def api_keys_delete(provider, key_name):
        """Delete a stored API key by provider and key name.

        Returns: {"status": "deleted"} or 404
        """
        with get_db() as db:
            deleted = delete_api_key(db, provider, key_name)
        if not deleted:
            return jsonify({"error": "Key not found"}), 404
        return jsonify({"status": "deleted"})

    @app.route("/api/api-keys/<provider>/<key_name>/cost")
    def api_keys_cost(provider, key_name):
        """Best-effort cost lookup for a stored API key.

        Returns: {balance_usd?, spend_usd?, currency?, error?, note?}

        Anthropic and OpenAI publish billing/credit data only on admin-scoped
        keys, so most regular API keys will get a "not accessible" note rather
        than a hard failure.
        """
        from open_uplift.keystore import get_api_key as _get_key
        with get_db() as db:
            api_key_val = _get_key(db, provider, key_name)
        if not api_key_val:
            return jsonify({"error": "Key not found"}), 404

        try:
            from open_uplift.cost_check import fetch_key_cost
            data = fetch_key_cost(provider, api_key_val)
            return jsonify(data)
        except Exception as e:
            return jsonify({"error": str(e)})

    @app.route("/api/api-keys/test", methods=["POST"])
    def api_keys_test():
        """Test an API key by making a lightweight LLM call.

        Body: {provider, api_key}
        Returns: {valid: bool, error?}
        """
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON body required"}), 400
        provider = data.get("provider")
        api_key_val = data.get("api_key")
        if not provider or not api_key_val:
            return jsonify({"error": "provider and api_key required"}), 400
        if provider == "anthropic":
            model = "claude-haiku-4-5-20251001"
        elif provider == "openrouter":
            model = "anthropic/claude-haiku-4-5-20251001"
        else:
            model = "gpt-4o-mini"
        try:
            client = LLMClient(provider, model, api_key_val)
            ok = client.test_connection()
            return jsonify({"valid": ok})
        except Exception as e:
            return jsonify({"valid": False, "error": str(e)})

    # --- Script Config (new nested format) ---

    def _default_script_config():
        return {
            "compaction": {
                "provider": "anthropic",
                "model": "claude-haiku-4-5-20251001",
                "prompt_id": "compaction-amy",
            },
            "judge": {
                "provider": "anthropic",
                "model": "claude-sonnet-4-5-20250929",
                "prompt_id": "judge-amy",
                "include_profile": False,
            },
        }

    def _read_script_config(db):
        cfg = _get_config(db, "script_config")
        return cfg if cfg else _default_script_config()

    @app.route("/api/script-config")
    def script_config_get():
        """Get the nested script config (compaction + judge settings).

        Returns: {compaction: {...}, judge: {...}}
        """
        with get_db() as db:
            config = _read_script_config(db)
        return jsonify(config)

    @app.route("/api/script-config", methods=["PUT"])
    def script_config_set():
        """Replace the nested script config.

        Body: {compaction: {...}, judge: {...}}
        Returns: the saved config
        """
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON body required"}), 400
        with get_db() as db:
            _set_config(db, "script_config", data)
        return jsonify(data)

    # --- Scaffolds (Phase 2) ---

    @app.route("/api/scaffolds")
    def scaffolds_list():
        """List all registered scaffolds.

        Returns: [{scaffold_id, display_name, description, created_at}]
        """
        with get_db() as db:
            rows = db.execute("SELECT scaffold_id, display_name, description, created_at FROM scaffolds").fetchall()
        return jsonify([dict(r) for r in rows])

    @app.route("/api/scaffolds", methods=["POST"])
    def scaffolds_create():
        """Register a new scaffold and generate its API token.

        Body: {display_name, description?}
        Returns: {scaffold_id, api_token} (201)
        """
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON body required"}), 400
        display_name = data.get("display_name")
        if not display_name:
            return jsonify({"error": "display_name required"}), 400
        scaffold_id = f"custom:{slugify(display_name)}"
        api_token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc).isoformat()
        with get_db() as db:
            try:
                db.execute(
                    "INSERT INTO scaffolds (scaffold_id, display_name, description, created_at, api_token) VALUES (?, ?, ?, ?, ?)",
                    (scaffold_id, display_name, data.get("description", ""), now, api_token),
                )
            except Exception:
                return jsonify({"error": "Scaffold already exists"}), 409
        return jsonify({"scaffold_id": scaffold_id, "api_token": api_token}), 201

    @app.route("/api/scaffolds/<scaffold_id>", methods=["DELETE"])
    def scaffolds_delete(scaffold_id):
        """Delete a scaffold by ID.

        Returns: {"status": "deleted"} or 404
        """
        with get_db() as db:
            cursor = db.execute("DELETE FROM scaffolds WHERE scaffold_id = ?", (scaffold_id,))
        if cursor.rowcount == 0:
            return jsonify({"error": "Scaffold not found"}), 404
        return jsonify({"status": "deleted"})

    @app.route("/api/ingest/session", methods=["POST"])
    def ingest_session():
        """Push a session from an external scaffold (bearer token auth)."""
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "Bearer token required"}), 401
        token = auth[7:]
        with get_db() as db:
            scaffold = db.execute(
                "SELECT scaffold_id FROM scaffolds WHERE api_token = ?", (token,)
            ).fetchone()
            if not scaffold:
                return jsonify({"error": "Invalid token"}), 401

            data = request.get_json()
            if not data:
                return jsonify({"error": "JSON body required"}), 400

            session_id = data.get("session_id")
            if not session_id:
                return jsonify({"error": "session_id required"}), 400

            now = datetime.now(timezone.utc).isoformat()
            db.execute(
                """INSERT INTO sessions
                   (session_id, tool_source, scaffold, project_path, project_name, git_branch,
                    started_at, ended_at, message_count, model_primary)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(session_id) DO UPDATE SET
                       ended_at = excluded.ended_at,
                       message_count = excluded.message_count""",
                (
                    session_id,
                    scaffold["scaffold_id"],
                    scaffold["scaffold_id"],
                    data.get("project_path"),
                    data.get("project_name"),
                    data.get("git_branch"),
                    data.get("started_at", now),
                    data.get("ended_at"),
                    data.get("message_count", 0),
                    data.get("model_primary"),
                ),
            )

            # Insert messages if provided
            for msg in data.get("messages", []):
                db.execute(
                    """INSERT INTO messages
                       (session_id, timestamp, role, model, input_tokens, output_tokens, tool_names)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        session_id,
                        msg.get("timestamp", now),
                        msg.get("role", "assistant"),
                        msg.get("model"),
                        msg.get("input_tokens", 0),
                        msg.get("output_tokens", 0),
                        msg.get("tool_names"),
                    ),
                )

        return jsonify({"status": "ingested", "session_id": session_id}), 201

    @app.route("/api/ingest/transcript", methods=["POST"])
    def ingest_transcript():
        """Push raw transcript JSONL for a session."""
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "Bearer token required"}), 401
        token = auth[7:]
        with get_db() as db:
            scaffold = db.execute(
                "SELECT scaffold_id FROM scaffolds WHERE api_token = ?", (token,)
            ).fetchone()
            if not scaffold:
                return jsonify({"error": "Invalid token"}), 401

        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON body required"}), 400
        session_id = data.get("session_id")
        lines = data.get("lines", [])
        if not session_id or not lines:
            return jsonify({"error": "session_id and lines required"}), 400

        scaffold_dir = CUSTOM_TRANSCRIPTS_DIR / scaffold["scaffold_id"]
        scaffold_dir.mkdir(parents=True, exist_ok=True)
        transcript_path = scaffold_dir / f"{session_id}.jsonl"
        with open(transcript_path, "w") as f:
            for line in lines:
                f.write(json.dumps(line) + "\n")

        return jsonify({"status": "stored", "path": str(transcript_path)}), 201

    # --- Prompts (Phase 3) ---

    @app.route("/api/prompts")
    def prompts_list():
        """List prompt templates, optionally filtered by category.

        Query: category (optional), include_archived (bool, default false)
        Returns: [{prompt_id, category, name, system_prompt, ...}]
        """
        category = request.args.get("category")
        include_archived = request.args.get("include_archived", "").lower() == "true"
        with get_db() as db:
            archive_filter = "" if include_archived else " AND archived_at IS NULL"
            if category:
                rows = db.execute(
                    f"SELECT * FROM prompts WHERE category = ?{archive_filter} ORDER BY is_default DESC, name",
                    (category,),
                ).fetchall()
            else:
                rows = db.execute(
                    f"SELECT * FROM prompts WHERE 1=1{archive_filter} ORDER BY category, is_default DESC, name"
                ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if d.get("output_schema"):
                d["output_schema"] = json.loads(d["output_schema"])
            result.append(d)
        return jsonify(result)

    @app.route("/api/prompts", methods=["POST"])
    def prompts_create():
        """Create a new prompt template.

        Body: {prompt_id, category, name, system_prompt, description?, output_schema?}
        Returns: {status, prompt_id} (201)
        """
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON body required"}), 400
        for field in ("prompt_id", "category", "name", "system_prompt"):
            if not data.get(field):
                return jsonify({"error": f"{field} required"}), 400
        now = datetime.now(timezone.utc).isoformat()
        schema_json = json.dumps(data["output_schema"]) if data.get("output_schema") else None
        with get_db() as db:
            try:
                db.execute(
                    """INSERT INTO prompts
                       (prompt_id, category, name, description, system_prompt, created_at,
                        is_default, output_schema, version)
                       VALUES (?, ?, ?, ?, ?, ?, 0, ?, 1)""",
                    (data["prompt_id"], data["category"], data["name"],
                     data.get("description", ""), data["system_prompt"], now, schema_json),
                )
            except Exception:
                return jsonify({"error": "Prompt ID already exists"}), 409
        return jsonify({"status": "created", "prompt_id": data["prompt_id"]}), 201

    @app.route("/api/prompts/<prompt_id>", methods=["PUT"])
    def prompts_update(prompt_id):
        """Create a new version of a prompt (archives the old one).

        Body: {name?, description?, system_prompt?, output_schema?}
        Returns: {status, new_prompt_id, version}
        """
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON body required"}), 400
        now = datetime.now(timezone.utc).isoformat()
        with get_db() as db:
            existing = db.execute("SELECT * FROM prompts WHERE prompt_id = ?", (prompt_id,)).fetchone()
            if not existing:
                return jsonify({"error": "Prompt not found"}), 404

            # Determine the base (logical) prompt_id for this version chain
            base_id = existing["parent_prompt_id"] or prompt_id

            # Archive the old row
            db.execute("UPDATE prompts SET archived_at = ? WHERE prompt_id = ?", (now, prompt_id))

            # Compute next version number across the chain
            max_ver = db.execute(
                "SELECT MAX(version) as mv FROM prompts WHERE prompt_id = ? OR parent_prompt_id = ?",
                (base_id, base_id),
            ).fetchone()["mv"] or 1
            next_ver = max_ver + 1
            new_prompt_id = f"{base_id}-v{next_ver}"

            # Build new row values, inheriting from existing unless overridden
            new_name = data.get("name", existing["name"])
            new_desc = data.get("description", existing["description"])
            new_system_prompt = data.get("system_prompt", existing["system_prompt"])
            if "output_schema" in data:
                new_schema = json.dumps(data["output_schema"]) if data["output_schema"] else None
            else:
                new_schema = existing["output_schema"]

            db.execute(
                """INSERT INTO prompts
                   (prompt_id, category, name, description, system_prompt, created_at,
                    is_default, output_schema, parent_prompt_id, version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (new_prompt_id, existing["category"], new_name, new_desc,
                 new_system_prompt, now, existing["is_default"], new_schema,
                 base_id, next_ver),
            )

            # Auto-update script_config if the old prompt_id was active
            cfg = _get_config(db, "script_config")
            if cfg:
                changed = False
                for section in cfg.values():
                    if isinstance(section, dict) and section.get("prompt_id") == prompt_id:
                        section["prompt_id"] = new_prompt_id
                        changed = True
                if changed:
                    _set_config(db, "script_config", cfg)

        return jsonify({"status": "updated", "new_prompt_id": new_prompt_id, "version": next_ver})

    @app.route("/api/prompts/<prompt_id>", methods=["DELETE"])
    def prompts_delete(prompt_id):
        """Soft-delete (archive) a prompt. Cannot delete defaults.

        Returns: {"status": "deleted"} or 400/404
        """
        now = datetime.now(timezone.utc).isoformat()
        with get_db() as db:
            existing = db.execute("SELECT * FROM prompts WHERE prompt_id = ?", (prompt_id,)).fetchone()
            if not existing:
                return jsonify({"error": "Prompt not found"}), 404
            if existing["is_default"]:
                return jsonify({"error": "Cannot delete default prompts"}), 400
            # Soft-delete: archive instead of removing
            db.execute("UPDATE prompts SET archived_at = ? WHERE prompt_id = ?", (now, prompt_id))

            # If this prompt is active in script_config, reset to the default for its category
            cfg = _get_config(db, "script_config")
            if cfg:
                category = existing["category"]
                defaults = _default_script_config()
                changed = False
                for section_key, section in cfg.items():
                    if isinstance(section, dict) and section.get("prompt_id") == prompt_id:
                        section["prompt_id"] = defaults.get(section_key, {}).get("prompt_id", f"{category}-default")
                        changed = True
                if changed:
                    _set_config(db, "script_config", cfg)

        return jsonify({"status": "deleted"})

    # --- Job Queue ---

    @app.route("/api/jobs")
    def jobs_list():
        """List background jobs, optionally filtered by status.

        Query: status (optional), limit (int, default 50)
        Returns: [{job_id, status, ...}]
        """
        status = request.args.get("status")
        limit = request.args.get("limit", 50, type=int)
        with get_db() as db:
            jobs = list_jobs(db, status=status, limit=limit)
        return jsonify(jobs)

    @app.route("/api/jobs/<job_id>")
    def job_detail(job_id):
        """Get details for a single background job.

        Returns: {job_id, status, payload, result, ...} or 404
        """
        with get_db() as db:
            job = get_job(db, job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        return jsonify(job)

    @app.route("/api/jobs/<job_id>/cancel", methods=["POST"])
    def job_cancel(job_id):
        """Cancel a pending or running job.

        Returns: {"status": "cancelled"} or 404
        """
        with get_db() as db:
            ok = cancel_job(db, job_id)
        if not ok:
            return jsonify({"error": "Job not found or not cancellable"}), 404
        return jsonify({"status": "cancelled"})

    # --- User Profile Config ---

    _DEFAULT_USER_PROFILE = {"experience_description": ""}

    @app.route("/api/config/user-profile")
    def user_profile_get():
        """Get the user profile configuration.

        Returns: {experience_description, ...}
        """
        with get_db() as db:
            profile = _get_config(db, "user_profile")
        return jsonify(profile or _DEFAULT_USER_PROFILE)

    @app.route("/api/config/user-profile", methods=["PUT"])
    def user_profile_set():
        """Update the user profile configuration.

        Body: {experience_description, ...}
        Returns: the saved profile
        """
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON body required"}), 400
        with get_db() as db:
            _set_config(db, "user_profile", data)
        return jsonify(data)

    # --- Run Mode Config ---

    @app.route("/api/config/run-modes")
    def run_modes_get():
        """Get script run mode config (manual, on-sync, scheduled).

        Returns: run mode configuration dict
        """
        with get_db() as db:
            config = _get_run_mode_config(db)
        return jsonify(config)

    @app.route("/api/config/run-modes", methods=["PUT"])
    def run_modes_set():
        """Update script run mode config and restart scheduler.

        Body: run mode configuration dict
        Returns: the saved config
        """
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON body required"}), 400
        with get_db() as db:
            _set_run_mode_config(db, data)
        update_scheduler_config()
        return jsonify(data)

    # --- Script Execution (Phase 3) ---

    @app.route("/api/scripts/run", methods=["POST"])
    def scripts_run():
        """Run a script (compaction or judge) on a single session.

        Body: {script_id, session_id}
        Returns: script result dict
        """
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON body required"}), 400
        script_id = data.get("script_id")
        session_id = data.get("session_id")
        if not script_id or not session_id:
            return jsonify({"error": "script_id and session_id required"}), 400
        with get_db() as db:
            # Check API key before running
            from open_uplift.scripts import _get_script_config
            from open_uplift.keystore import get_api_key as _get_key
            cfg = _get_script_config(db)
            for role in ("compaction", "judge"):
                provider = cfg.get(role, {}).get("provider", "anthropic")
                if not _get_key(db, provider):
                    return jsonify({"error": f"No API key configured for {provider}. Add one in Settings → API Keys."}), 400
            result = run_script(db, script_id, session_id)
        return jsonify(result)

    @app.route("/api/scripts/results/<session_id>")
    def scripts_results(session_id):
        """Get all script results for a session.

        Returns: [{script_id, status, result, ...}]
        """
        with get_db() as db:
            results = get_script_results(db, session_id)
        return jsonify(results)

    @app.route("/api/scripts/run-batch", methods=["POST"])
    def scripts_run_batch():
        """Async batch execution — enqueues a job and returns its ID."""
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON body required"}), 400
        scripts = data.get("scripts", [])
        session_ids = data.get("session_ids", [])
        # Backward compat: accept single script_id
        if not scripts and data.get("script_id"):
            scripts = [data["script_id"]]
        if not scripts or not session_ids:
            return jsonify({"error": "scripts and session_ids required"}), 400
        with get_db() as db:
            # Check API key before enqueuing
            from open_uplift.scripts import _get_script_config
            from open_uplift.keystore import get_api_key as _get_key
            cfg = _get_script_config(db)
            for role in ("compaction", "judge"):
                provider = cfg.get(role, {}).get("provider", "anthropic")
                if not _get_key(db, provider):
                    return jsonify({"error": f"No API key configured for {provider}. Add one in Settings → API Keys."}), 400
            job_id = enqueue_job(db, "script-batch", {"scripts": scripts, "session_ids": session_ids})
        return jsonify({"job_id": job_id}), 202

    @app.route("/api/scripts/unprocessed-count")
    def scripts_unprocessed_count():
        """Return the number of sessions needing processing."""
        with get_db() as db:
            ids = _find_unprocessed_session_ids(db)
        return jsonify({"count": len(ids)})

    @app.route("/api/scripts/run-unprocessed", methods=["POST"])
    def scripts_run_unprocessed():
        """Find all sessions missing script results and enqueue a batch job."""
        # Check API key before enqueuing
        from open_uplift.scripts import _get_script_config
        from open_uplift.keystore import get_api_key as _get_key
        with get_db() as db:
            cfg = _get_script_config(db)
            for role in ("compaction", "judge"):
                provider = cfg.get(role, {}).get("provider", "anthropic")
                if not _get_key(db, provider):
                    return jsonify({"error": f"No API key configured for {provider}. Add one in Settings → API Keys."}), 400
        job_id, count = _enqueue_unprocessed()
        if not job_id:
            return jsonify({"job_id": None, "session_count": 0})
        return jsonify({"job_id": job_id, "session_count": count}), 202


    @app.route("/api/evaluators")
    def list_evaluators():
        """List all registered evaluators."""
        from open_uplift.evaluators.registry import get_registry
        registry = get_registry()
        return jsonify(registry.list_available())

    # --- Time Measurement (Phase 4) ---

    @app.route("/api/sessions/<session_id>/time")
    def session_time(session_id):
        """Compute time-with-AI and concurrency adjustment for a session.

        Returns: {time, concurrency}
        """
        with get_db() as db:
            time_data = compute_time_with_ai(db, session_id)
            concurrency = compute_concurrency_adjustment(db, session_id)
        return jsonify({
            "time": time_data,
            "concurrency": concurrency,
        })

    # --- Judge Outputs ---

    @app.route("/api/sessions/<session_id>/judge-outputs")
    def session_judge_outputs(session_id):
        """Return judge outputs for a session."""
        with get_db() as db:
            rows = db.execute(
                "SELECT field_name, value_text, value_numeric, value_type, prompt_id, created_at FROM judge_outputs WHERE session_id = ? ORDER BY field_name",
                (session_id,),
            ).fetchall()
        outputs = {}
        for r in rows:
            d = dict(r)
            # Parse value based on type
            if d["value_type"] == "boolean":
                d["value"] = d["value_text"] == "true"
            elif d["value_type"] == "numeric":
                d["value"] = d["value_numeric"]
            elif d["value_type"] == "array":
                try:
                    d["value"] = json.loads(d["value_text"])
                except (json.JSONDecodeError, TypeError):
                    d["value"] = d["value_text"]
            else:
                d["value"] = d["value_text"]
            outputs[d["field_name"]] = d
        return jsonify(outputs)

    @app.route("/api/judge-outputs/summary")
    def judge_outputs_summary():
        """Aggregated stats per field across all sessions."""
        org_id = request.args.get("org_id")
        with get_db() as db:
            org_join = ""
            org_clause = ""
            org_params: list = []
            if org_id:
                cond, org_params = _org_folder_filter(db, org_id)
                if cond is None:
                    return jsonify([])
                org_join = " JOIN sessions s ON s.session_id = jo.session_id"
                org_clause = f" AND {cond}"

            rows = db.execute(
                f"""SELECT jo.field_name, jo.value_type,
                          COUNT(*) as count,
                          AVG(jo.value_numeric) as avg_numeric,
                          SUM(CASE WHEN jo.value_text = 'true' THEN 1 ELSE 0 END) as true_count
                   FROM judge_outputs jo{org_join}
                   WHERE 1=1{org_clause}
                   GROUP BY jo.field_name, jo.value_type
                   ORDER BY jo.field_name""",
                org_params,
            ).fetchall()
            total_judged = db.execute(
                f"""SELECT COUNT(DISTINCT jo.session_id) as c
                   FROM judge_outputs jo{org_join}
                   WHERE 1=1{org_clause}""",
                org_params,
            ).fetchone()
        summary = []
        for r in rows:
            d = dict(r)
            if d["value_type"] == "boolean":
                d["rate"] = round(d["true_count"] / d["count"], 4) if d["count"] > 0 else 0
            if d["value_type"] == "numeric" and d["avg_numeric"] is not None:
                d["avg_numeric"] = round(d["avg_numeric"], 2)
            summary.append(d)
        return jsonify({"fields": summary, "total_judged_sessions": total_judged["c"]})

    # --- Uplift Analytics (Phase 5) ---

    def _org_folder_filter(db, org_id):
        """Return (sql_condition, params) for filtering sessions by org folders.

        When org_id == "local", returns a condition for all local sessions.
        When org_id == "personal", returns a condition that *excludes* sessions
        in any org folder (i.e. only personal sessions).

        Returns (None, []) when the org has no folders, signalling the caller
        should return empty results.
        """
        if org_id == "local":
            return "s.is_local = 1", []
        if org_id == "personal":
            return (
                "NOT EXISTS (SELECT 1 FROM org_folders of2"
                " WHERE s.project_path = of2.folder_path"
                " OR s.project_path LIKE of2.folder_path || '/%')"
            ), []

        folders = db.execute(
            "SELECT folder_path FROM org_folders WHERE org_id = ?", (org_id,)
        ).fetchall()
        folder_paths = [f["folder_path"] for f in folders]
        if not folder_paths:
            return None, []
        path_conditions = " OR ".join(
            ["(s.project_path = ? OR s.project_path LIKE ? || '/%')"] * len(folder_paths)
        )
        path_params = []
        for fp in folder_paths:
            path_params.extend([fp, fp])
        return f"({path_conditions})", path_params

    def _build_distribution_response(values):
        """Build distribution response from a list of uplift values."""
        if not values:
            return {"buckets": [], "values": [], "stats": {}}
        import math
        min_v, max_v = min(values), max(values)
        bucket_size = max(0.5, (max_v - min_v) / 20) if max_v > min_v else 0.5
        buckets = []
        lo = math.floor(min_v / bucket_size) * bucket_size
        while lo <= max_v:
            hi = lo + bucket_size
            count = sum(1 for v in values if lo <= v < hi)
            buckets.append({"lo": round(lo, 2), "hi": round(hi, 2), "count": count})
            lo = hi
        avg = sum(values) / len(values)
        median = sorted(values)[len(values) // 2]
        return {
            "buckets": buckets,
            "values": values,
            "stats": {"count": len(values), "avg": round(avg, 2), "median": round(median, 2), "min": min_v, "max": max_v},
        }

    @app.route("/api/uplift/distribution")
    def uplift_distribution():
        """Uplift factor distribution with histogram buckets and stats.

        Query: output_id (default "llm-judge"), org_id (optional)
        Returns: {buckets, values, stats}
        """
        output_id = request.args.get("output_id", "llm-judge")
        org_id = request.args.get("org_id")
        with get_db() as db:
            org_clause = ""
            org_params: list = []
            if org_id:
                cond, org_params = _org_folder_filter(db, org_id)
                if cond is None:
                    # No local folders — but may have hub data
                    org_clause = " AND 1=0"  # no local results
                else:
                    org_clause = f" AND {cond}"

            rows = db.execute(
                f"""SELECT uo.uplift_factor FROM uplift_outputs uo
                   JOIN sessions s ON s.session_id = uo.session_id
                   LEFT JOIN judge_outputs jo ON jo.session_id = uo.session_id AND jo.field_name = 'success'
                   WHERE uo.output_id = ?
                     AND (jo.id IS NULL OR jo.value_text = 'true')
                     {org_clause}
                   ORDER BY uo.uplift_factor""",
                (output_id, *org_params),
            ).fetchall()
            values = [r["uplift_factor"] for r in rows]

            # For hub orgs, merge member aggregate uplift values
            if org_id:
                org_row = db.execute("SELECT org_mode FROM organizations WHERE org_id = ?", (org_id,)).fetchone()
                if org_row and (org_row["org_mode"] or "hub") == "hub":
                    agg_rows = db.execute(
                        "SELECT aggregate_data FROM hub_aggregates WHERE org_id = ?", (org_id,)
                    ).fetchall()
                    combined = _combine_hub_aggregates(agg_rows)
                    values.extend(combined.get("uplift_values", []))

        return jsonify(_build_distribution_response(values))

    @app.route("/api/uplift/timeseries")
    def uplift_timeseries():
        """Daily average uplift factor over time.

        Query: output_id (default "llm-judge"), days (default 90)
        Returns: [{day, avg_uplift, count}]
        """
        output_id = request.args.get("output_id", "llm-judge")
        days = request.args.get("days", "90", type=str)
        with get_db() as db:
            rows = db.execute(
                """SELECT date(uo.timestamp) as day,
                          ROUND(AVG(uo.uplift_factor), 2) as avg_uplift,
                          COUNT(*) as count
                   FROM uplift_outputs uo
                   LEFT JOIN judge_outputs jo ON jo.session_id = uo.session_id AND jo.field_name = 'success'
                   WHERE uo.output_id = ?
                     AND uo.timestamp >= datetime('now', ?)
                     AND (jo.id IS NULL OR jo.value_text = 'true')
                   GROUP BY date(uo.timestamp)
                   ORDER BY day""",
                (output_id, f"-{days} days"),
            ).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.route("/api/uplift/by-project")
    def uplift_by_project():
        """Average uplift factor grouped by project.

        Query: output_id (default "llm-judge"), org_id (optional)
        Returns: [{project_name, avg_uplift, count}]
        """
        output_id = request.args.get("output_id", "llm-judge")
        org_id = request.args.get("org_id")
        with get_db() as db:
            org_clause = ""
            org_params: list = []
            if org_id:
                cond, org_params = _org_folder_filter(db, org_id)
                if cond is None:
                    return jsonify([])
                org_clause = f" AND {cond}"

            rows = db.execute(
                f"""SELECT s.project_name, ROUND(AVG(uo.uplift_factor), 2) as avg_uplift, COUNT(*) as count
                   FROM uplift_outputs uo
                   JOIN sessions s ON s.session_id = uo.session_id
                   LEFT JOIN judge_outputs jo ON jo.session_id = uo.session_id AND jo.field_name = 'success'
                   WHERE uo.output_id = ? AND s.project_name IS NOT NULL
                     AND (jo.id IS NULL OR jo.value_text = 'true')
                     {org_clause}
                   GROUP BY s.project_name
                   ORDER BY avg_uplift DESC""",
                (output_id, *org_params),
            ).fetchall()
        return jsonify([dict(r) for r in rows])

    def _merge_by_group(local_rows, hub_entries, group_key):
        """Merge local query results with hub aggregate breakdown using weighted averages."""
        merged: dict[str, dict] = {}
        for r in local_rows:
            key = r[group_key] or "unknown"
            merged[key] = {"sum": r["avg_uplift"] * r["count"], "count": r["count"]}
        for entry in hub_entries:
            key = entry.get(group_key, "unknown") or "unknown"
            cnt = entry.get("count", 0)
            avg = entry.get("avg_uplift", 0)
            if key not in merged:
                merged[key] = {"sum": 0.0, "count": 0}
            merged[key]["sum"] += avg * cnt
            merged[key]["count"] += cnt
        return [
            {group_key: k, "avg_uplift": round(v["sum"] / v["count"], 2), "count": v["count"]}
            for k, v in sorted(merged.items(), key=lambda x: x[1]["sum"] / max(x[1]["count"], 1), reverse=True)
            if v["count"] > 0
        ]

    @app.route("/api/uplift/by-scaffold")
    def uplift_by_scaffold():
        """Average uplift factor grouped by scaffold/tool source.

        Query: output_id (default "llm-judge"), org_id (optional)
        Returns: [{scaffold, avg_uplift, count}]
        """
        output_id = request.args.get("output_id", "llm-judge")
        org_id = request.args.get("org_id")
        with get_db() as db:
            org_clause = ""
            org_params: list = []
            if org_id:
                cond, org_params = _org_folder_filter(db, org_id)
                if cond is None:
                    org_clause = " AND 1=0"
                else:
                    org_clause = f" AND {cond}"

            rows = db.execute(
                f"""SELECT COALESCE(s.scaffold, s.tool_source) as scaffold,
                          ROUND(AVG(uo.uplift_factor), 2) as avg_uplift, COUNT(*) as count
                   FROM uplift_outputs uo
                   JOIN sessions s ON s.session_id = uo.session_id
                   LEFT JOIN judge_outputs jo ON jo.session_id = uo.session_id AND jo.field_name = 'success'
                   WHERE uo.output_id = ?
                     AND (jo.id IS NULL OR jo.value_text = 'true')
                     {org_clause}
                   GROUP BY scaffold
                   ORDER BY avg_uplift DESC""",
                (output_id, *org_params),
            ).fetchall()

            # For hub orgs, merge member aggregate data
            if org_id:
                org_row = db.execute("SELECT org_mode FROM organizations WHERE org_id = ?", (org_id,)).fetchone()
                if org_row and (org_row["org_mode"] or "hub") == "hub":
                    agg_rows = db.execute(
                        "SELECT aggregate_data FROM hub_aggregates WHERE org_id = ?", (org_id,)
                    ).fetchall()
                    combined = _combine_hub_aggregates(agg_rows)
                    return jsonify(_merge_by_group(rows, combined.get("by_scaffold", []), "scaffold"))

        return jsonify([dict(r) for r in rows])

    @app.route("/api/uplift/by-model")
    def uplift_by_model():
        """Average uplift factor grouped by primary model.

        Query: output_id (default "llm-judge"), org_id (optional)
        Returns: [{model, avg_uplift, count}]
        """
        output_id = request.args.get("output_id", "llm-judge")
        org_id = request.args.get("org_id")
        with get_db() as db:
            org_clause = ""
            org_params: list = []
            if org_id:
                cond, org_params = _org_folder_filter(db, org_id)
                if cond is None:
                    org_clause = " AND 1=0"
                else:
                    org_clause = f" AND {cond}"

            rows = db.execute(
                f"""SELECT s.model_primary as model,
                          ROUND(AVG(uo.uplift_factor), 2) as avg_uplift, COUNT(*) as count
                   FROM uplift_outputs uo
                   JOIN sessions s ON s.session_id = uo.session_id
                   LEFT JOIN judge_outputs jo ON jo.session_id = uo.session_id AND jo.field_name = 'success'
                   WHERE uo.output_id = ? AND s.model_primary IS NOT NULL
                     AND (jo.id IS NULL OR jo.value_text = 'true')
                     {org_clause}
                   GROUP BY s.model_primary
                   ORDER BY avg_uplift DESC""",
                (output_id, *org_params),
            ).fetchall()

            # For hub orgs, merge member aggregate data
            if org_id:
                org_row = db.execute("SELECT org_mode FROM organizations WHERE org_id = ?", (org_id,)).fetchone()
                if org_row and (org_row["org_mode"] or "hub") == "hub":
                    agg_rows = db.execute(
                        "SELECT aggregate_data FROM hub_aggregates WHERE org_id = ?", (org_id,)
                    ).fetchall()
                    combined = _combine_hub_aggregates(agg_rows)
                    return jsonify(_merge_by_group(rows, combined.get("by_model", []), "model"))

        return jsonify([dict(r) for r in rows])

    @app.route("/api/uplift/agreement")
    def uplift_agreement():
        """Compare human self-report vs LLM judge uplift for sessions with both.

        Returns: [{session_id, human, llm}]
        """
        with get_db() as db:
            rows = db.execute(
                """SELECT uo.session_id,
                          MAX(CASE WHEN uo.output_id = 'human-est' THEN uo.uplift_factor END) as human,
                          MAX(CASE WHEN uo.output_id IN ('llm-judge-trans', 'llm-judge') THEN uo.uplift_factor END) as llm
                   FROM uplift_outputs uo
                   WHERE uo.session_id IS NOT NULL
                   GROUP BY uo.session_id
                   HAVING human IS NOT NULL AND llm IS NOT NULL"""
            ).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.route("/api/uplift/concurrency")
    def uplift_concurrency():
        """Uplift factors with concurrent session counts and adjusted minutes.

        Query: output_id (default "llm-judge")
        Returns: [{session_id, uplift_factor, concurrent_sessions, adjusted_minutes}]
        """
        output_id = request.args.get("output_id", "llm-judge")
        with get_db() as db:
            rows = db.execute(
                """SELECT uo.session_id, uo.uplift_factor
                   FROM uplift_outputs uo
                   WHERE uo.output_id = ? AND uo.session_id IS NOT NULL""",
                (output_id,),
            ).fetchall()
            results = []
            for r in rows:
                concurrency = compute_concurrency_adjustment(db, r["session_id"])
                results.append({
                    "session_id": r["session_id"],
                    "uplift_factor": r["uplift_factor"],
                    "concurrent_sessions": concurrency["concurrent_sessions"],
                    "adjusted_minutes": concurrency["adjusted_minutes"],
                })
        return jsonify(results)

    # --- Organizations ---

    @app.route("/api/organizations")
    def organizations_list():
        """List all organizations with folder counts.

        Returns: [{org_id, name, folder_count, ...}]
        """
        with get_db() as db:
            rows = db.execute(
                """SELECT o.*, COUNT(of2.id) as folder_count
                   FROM organizations o
                   LEFT JOIN org_folders of2 ON o.org_id = of2.org_id
                   GROUP BY o.org_id
                   ORDER BY o.name"""
            ).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.route("/api/organizations", methods=["POST"])
    def create_organization():
        """Create a new organization with admin member and invite code.

        Body: {name, description?, folder_paths?}
        Returns: {org_id, name, org_mode, invite_code, api_key} (201)
        """
        data = request.get_json()
        if not data or not data.get("name"):
            return jsonify({"error": "name is required"}), 400
        org_id = slugify(data["name"])
        if not org_id:
            return jsonify({"error": "name must contain at least one alphanumeric character"}), 400
        org_mode = "hub"
        now = datetime.now(timezone.utc).isoformat()
        with get_db() as db:
            existing = db.execute("SELECT 1 FROM organizations WHERE org_id = ?", (org_id,)).fetchone()
            if existing:
                return jsonify({"error": f"Organization '{data['name']}' already exists"}), 409
            # Validate folder conflicts BEFORE creating the org
            folder_paths = data.get("folder_paths", [])
            for fp in folder_paths:
                conflict = db.execute(
                    """SELECT of2.org_id FROM org_folders of2
                       WHERE of2.folder_path = ?
                          OR of2.folder_path LIKE ? || '/%'
                          OR ? LIKE of2.folder_path || '/%'""",
                    (fp, fp, fp),
                ).fetchone()
                if conflict:
                    return jsonify({"error": f"Folder '{fp}' conflicts with org '{conflict['org_id']}'"}), 409
            db.execute(
                "INSERT INTO organizations (org_id, name, description, is_verified, created_at, sharing_config, org_mode) VALUES (?, ?, ?, 0, ?, ?, ?)",
                (org_id, data["name"], data.get("description", ""), now, json.dumps(DEFAULT_SHARING_CONFIG), org_mode),
            )
            # Auto-create hub admin + invite
            member_name = "admin"
            api_key = secrets.token_urlsafe(32)
            db.execute(
                "INSERT INTO hub_members (org_id, member_name, api_key, role, joined_at) VALUES (?, ?, ?, 'admin', ?)",
                (org_id, member_name, api_key, now),
            )
            invite_code = secrets.token_urlsafe(16)
            db.execute(
                "INSERT INTO hub_invites (invite_code, org_id, created_by, created_at) VALUES (?, ?, ?, ?)",
                (invite_code, org_id, member_name, now),
            )
            for fp in folder_paths:
                db.execute(
                    "INSERT INTO org_folders (org_id, folder_path, added_at) VALUES (?, ?, ?)",
                    (org_id, fp, now),
                )
        return jsonify({"org_id": org_id, "name": data["name"], "org_mode": org_mode, "invite_code": invite_code, "api_key": api_key}), 201

    @app.route("/api/organizations/<org_id>")
    def organization_detail(org_id):
        """Get organization details, folders, stats, and push/pull counts.

        Returns: {org_id, name, folders, stats, unpushed_count, ...}
        """
        with get_db() as db:
            org = db.execute("SELECT * FROM organizations WHERE org_id = ?", (org_id,)).fetchone()
            if not org:
                return jsonify({"error": "not found"}), 404
            folders = db.execute(
                "SELECT folder_path, added_at FROM org_folders WHERE org_id = ? ORDER BY folder_path",
                (org_id,),
            ).fetchall()
            # Aggregate stats across all org folders (subfolder inheritance)
            folder_paths = [f["folder_path"] for f in folders]
            if folder_paths:
                path_conditions = " OR ".join(
                    ["(project_path = ? OR project_path LIKE ? || '/%')"] * len(folder_paths)
                )
                path_params = []
                for fp in folder_paths:
                    path_params.extend([fp, fp])
                stats = db.execute(
                    f"""SELECT
                         COUNT(*) as total_sessions,
                         COALESCE(SUM(total_input_tokens + total_output_tokens), 0) as total_tokens,
                         COALESCE(SUM(message_count), 0) as total_messages,
                         COALESCE(SUM(total_cost_usd), 0) as total_cost
                       FROM sessions
                       WHERE {path_conditions}""",
                    path_params,
                ).fetchone()
            else:
                stats = {"total_sessions": 0, "total_tokens": 0, "total_messages": 0, "total_cost": 0}

            # Unpushed count: sessions in org folders where updated_at > last_push_at
            unpushed_count = 0
            judged_unpushed_count = 0
            needs_judging_count = 0
            org_mode = org["org_mode"] or "hub"
            if org_mode in ("hub", "member") and folder_paths:
                membership_row = db.execute(
                    "SELECT last_push_at FROM org_memberships WHERE org_id = ?", (org_id,)
                ).fetchone()
                last_push = membership_row["last_push_at"] if membership_row else None

                unpushed_where = f"COALESCE(s.is_local, 1) = 1 AND ({path_conditions})"
                unpushed_params = list(path_params)
                if last_push:
                    unpushed_where += " AND s.updated_at > ?"
                    unpushed_params.append(last_push)

                unpushed = db.execute(
                    f"SELECT COUNT(*) as c FROM sessions s WHERE {unpushed_where}",
                    unpushed_params,
                ).fetchone()
                unpushed_count = unpushed["c"] if unpushed else 0

                # Judged unpushed: have current llm-time-estimate
                judged = db.execute(
                    f"""SELECT COUNT(*) as c FROM sessions s
                       JOIN script_results sr ON sr.session_id = s.session_id
                           AND sr.script_id = 'llm-time-estimate'
                           AND sr.status = 'completed'
                           AND sr.session_message_count >= s.message_count
                       WHERE {unpushed_where}""",
                    unpushed_params,
                ).fetchone()
                judged_unpushed_count = judged["c"] if judged else 0
                needs_judging_count = unpushed_count - judged_unpushed_count

            # Pulled session count
            pulled_count = db.execute(
                "SELECT COUNT(*) as c FROM sessions WHERE is_local = 0 AND source_org_id = ?",
                (org_id,),
            ).fetchone()
            pulled_session_count = pulled_count["c"] if pulled_count else 0

            # Pushed sessions count: prefer hub_sessions (actual per-session data),
            # fall back to aggregate total_sessions for aggregate-only members
            hub_sess_count = db.execute(
                "SELECT COUNT(*) as c FROM hub_sessions WHERE org_id = ?", (org_id,)
            ).fetchone()
            hub_sess_total = hub_sess_count["c"] if hub_sess_count else 0

            if hub_sess_total > 0:
                pushed_sessions_count = hub_sess_total
            else:
                # Aggregate-only mode: sum total_sessions from hub_aggregates
                agg_rows = db.execute(
                    "SELECT aggregate_data FROM hub_aggregates WHERE org_id = ?",
                    (org_id,),
                ).fetchall()
                pushed_sessions_count = 0
                for agg_row in agg_rows:
                    try:
                        agg_data = json.loads(agg_row["aggregate_data"]) if isinstance(agg_row["aggregate_data"], str) else agg_row["aggregate_data"]
                        pushed_sessions_count += agg_data.get("total_sessions", 0)
                    except (json.JSONDecodeError, TypeError):
                        pass

        return jsonify({
            **dict(org),
            "folders": [dict(f) for f in folders],
            "stats": dict(stats) if not isinstance(stats, dict) else stats,
            "unpushed_count": unpushed_count,
            "judged_unpushed_count": judged_unpushed_count,
            "needs_judging_count": needs_judging_count,
            "pulled_session_count": pulled_session_count,
            "pushed_sessions_count": pushed_sessions_count,
            "pushed_aggregate_only": hub_sess_total == 0 and pushed_sessions_count > 0,
        })

    @app.route("/api/organizations/<org_id>", methods=["PUT"])
    def update_organization(org_id):
        """Update organization name, description, or verification status.

        Body: {name?, description?, is_verified?}
        Returns: {"status": "updated"}
        """
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON body required"}), 400
        with get_db() as db:
            org = db.execute("SELECT 1 FROM organizations WHERE org_id = ?", (org_id,)).fetchone()
            if not org:
                return jsonify({"error": "not found"}), 404
            updates = []
            params = []
            for field in ("name", "description"):
                if field in data:
                    updates.append(f"{field} = ?")
                    params.append(data[field])
            if "is_verified" in data:
                updates.append("is_verified = ?")
                params.append(1 if data["is_verified"] else 0)
            if not updates:
                return jsonify({"error": "no fields to update"}), 400
            params.append(org_id)
            db.execute(f"UPDATE organizations SET {', '.join(updates)} WHERE org_id = ?", params)
        return jsonify({"status": "updated"})

    @app.route("/api/organizations/<org_id>", methods=["DELETE"])
    def delete_organization(org_id):
        """Delete an organization and all related hub/membership data.

        Returns: {"status": "deleted"} or 404
        """
        with get_db() as db:
            org = db.execute("SELECT org_id, name, org_mode FROM organizations WHERE org_id = ?", (org_id,)).fetchone()
            if not org:
                return jsonify({"error": "not found"}), 404
            mode = org["org_mode"] or "hub"
            if mode == "hub":
                db.execute("DELETE FROM hub_members WHERE org_id = ?", (org_id,))
                db.execute("DELETE FROM hub_invites WHERE org_id = ?", (org_id,))
                db.execute("DELETE FROM hub_sessions WHERE org_id = ?", (org_id,))
                db.execute("DELETE FROM hub_aggregates WHERE org_id = ?", (org_id,))
            elif mode == "member":
                db.execute("DELETE FROM org_memberships WHERE org_id = ?", (org_id,))
            db.execute("DELETE FROM organizations WHERE org_id = ?", (org_id,))
        return jsonify({"status": "deleted"})

    @app.route("/api/organizations/<org_id>/folders", methods=["POST"])
    def add_org_folders(org_id):
        """Add folder paths to an organization, checking for cross-org conflicts.

        Body: {folder_paths: [str]}
        Returns: {"status": "added"} or 409 on conflict
        """
        data = request.get_json()
        if not data or not data.get("folder_paths"):
            return jsonify({"error": "folder_paths required"}), 400
        now = datetime.now(timezone.utc).isoformat()
        with get_db() as db:
            org = db.execute("SELECT 1 FROM organizations WHERE org_id = ?", (org_id,)).fetchone()
            if not org:
                return jsonify({"error": "not found"}), 404
            for fp in data["folder_paths"]:
                # Check cross-org conflicts including parent/child overlaps
                conflict = db.execute(
                    """SELECT of2.org_id FROM org_folders of2
                       WHERE of2.folder_path = ?
                          OR of2.folder_path LIKE ? || '/%'
                          OR ? LIKE of2.folder_path || '/%'""",
                    (fp, fp, fp),
                ).fetchone()
                if conflict and conflict["org_id"] != org_id:
                    return jsonify({"error": f"Folder '{fp}' conflicts with org '{conflict['org_id']}'"}), 409
                db.execute(
                    "INSERT OR IGNORE INTO org_folders (org_id, folder_path, added_at) VALUES (?, ?, ?)",
                    (org_id, fp, now),
                )
        return jsonify({"status": "added"})

    @app.route("/api/organizations/<org_id>/remove-folders", methods=["POST"])
    def remove_org_folders(org_id):
        """Remove folder paths from an organization.

        Body: {folder_paths: [str]}
        Returns: {"status": "removed"}
        """
        data = request.get_json()
        if not data or not data.get("folder_paths"):
            return jsonify({"error": "folder_paths required"}), 400
        with get_db() as db:
            for fp in data["folder_paths"]:
                db.execute(
                    "DELETE FROM org_folders WHERE org_id = ? AND folder_path = ?",
                    (org_id, fp),
                )
        return jsonify({"status": "removed"})

    @app.route("/api/organizations/unassigned-folders")
    def unassigned_folders():
        """List project paths not assigned to any organization (excluding dismissed).

        Returns: [{project_path, project_name}]
        """
        with get_db() as db:
            # Get all distinct project paths
            all_projects = db.execute(
                """SELECT DISTINCT project_path, project_name
                   FROM sessions
                   WHERE project_path IS NOT NULL"""
            ).fetchall()
            # Get all org folder paths
            org_folder_rows = db.execute("SELECT folder_path FROM org_folders").fetchall()
            org_paths = [r["folder_path"] for r in org_folder_rows]
            # Get dismissed paths
            dismissed = db.execute("SELECT folder_path FROM org_prompt_dismissed").fetchall()
            dismissed_set = {r["folder_path"] for r in dismissed}

            unassigned = []
            for p in all_projects:
                pp = p["project_path"]
                if pp in dismissed_set:
                    continue
                # Check if this path or any parent is in an org
                in_org = False
                for op in org_paths:
                    if pp == op or pp.startswith(op + "/"):
                        in_org = True
                        break
                if not in_org:
                    unassigned.append({
                        "project_path": pp,
                        "project_name": p["project_name"],
                    })
        return jsonify(unassigned)

    @app.route("/api/organizations/dismiss-folder", methods=["POST"])
    def dismiss_folder():
        """Dismiss an unassigned folder from the org assignment prompt.

        Body: {folder_path}
        Returns: {"status": "dismissed"}
        """
        data = request.get_json()
        if not data or not data.get("folder_path"):
            return jsonify({"error": "folder_path required"}), 400
        now = datetime.now(timezone.utc).isoformat()
        with get_db() as db:
            db.execute(
                "INSERT OR REPLACE INTO org_prompt_dismissed (folder_path, dismissed_at) VALUES (?, ?)",
                (data["folder_path"], now),
            )
        return jsonify({"status": "dismissed"})

    @app.route("/api/organizations/<org_id>/analytics")
    def organization_analytics(org_id):
        """Detailed analytics for an organization: totals, uplift, daily breakdown.

        Query: output_id (default "llm-judge"), days (default 90)
        Returns: {totals, uplift, daily, uplift_timeseries}
        """
        output_id = request.args.get("output_id", "llm-judge")
        days = request.args.get("days", "90", type=str)
        with get_db() as db:
            org = db.execute("SELECT 1 FROM organizations WHERE org_id = ?", (org_id,)).fetchone()
            if not org:
                return jsonify({"error": "not found"}), 404
            folders = db.execute(
                "SELECT folder_path FROM org_folders WHERE org_id = ?", (org_id,)
            ).fetchall()
            folder_paths = [f["folder_path"] for f in folders]

            if not folder_paths:
                return jsonify({
                    "totals": {"total_sessions": 0, "total_tokens": 0, "total_messages": 0, "total_tool_calls": 0, "total_cost": 0},
                    "uplift": {"count": 0, "avg_uplift": 0},
                    "daily": [],
                    "uplift_timeseries": [],
                })

            path_conditions = " OR ".join(
                ["(s.project_path = ? OR s.project_path LIKE ? || '/%')"] * len(folder_paths)
            )
            path_params = []
            for fp in folder_paths:
                path_params.extend([fp, fp])

            # Aggregate totals
            totals = db.execute(
                f"""SELECT
                     COUNT(*) as total_sessions,
                     COALESCE(SUM(s.total_input_tokens + s.total_output_tokens), 0) as total_tokens,
                     COALESCE(SUM(s.message_count), 0) as total_messages,
                     COALESCE(SUM(s.tool_call_count), 0) as total_tool_calls,
                     COALESCE(SUM(s.total_cost_usd), 0) as total_cost
                   FROM sessions s
                   WHERE {path_conditions}""",
                path_params,
            ).fetchone()

            # Uplift stats (filter to successful sessions only, matching global endpoints)
            uplift = db.execute(
                f"""SELECT COUNT(*) as count, ROUND(COALESCE(AVG(uo.uplift_factor), 0), 2) as avg_uplift
                   FROM uplift_outputs uo
                   JOIN sessions s ON s.session_id = uo.session_id
                   LEFT JOIN judge_outputs jo ON jo.session_id = uo.session_id AND jo.field_name = 'success'
                   WHERE uo.output_id = ?
                     AND (jo.id IS NULL OR jo.value_text = 'true')
                     AND ({path_conditions})""",
                (output_id, *path_params),
            ).fetchone()

            # Daily breakdown
            daily = db.execute(
                f"""SELECT
                     date(s.started_at) as day,
                     COUNT(*) as sessions,
                     COALESCE(SUM(s.total_input_tokens + s.total_output_tokens), 0) as tokens,
                     COALESCE(SUM(s.total_cost_usd), 0) as cost
                   FROM sessions s
                   WHERE s.started_at >= datetime('now', ?)
                     AND ({path_conditions})
                   GROUP BY date(s.started_at)
                   ORDER BY day""",
                (f"-{days} days", *path_params),
            ).fetchall()

            # Uplift timeseries
            uplift_ts = db.execute(
                f"""SELECT
                     date(uo.timestamp) as day,
                     AVG(uo.uplift_factor) as avg_uplift,
                     COUNT(*) as count
                   FROM uplift_outputs uo
                   JOIN sessions s ON s.session_id = uo.session_id
                   WHERE uo.output_id = ?
                     AND uo.timestamp >= datetime('now', ?)
                     AND ({path_conditions})
                   GROUP BY date(uo.timestamp)
                   ORDER BY day""",
                (output_id, f"-{days} days", *path_params),
            ).fetchall()

        return jsonify({
            "totals": dict(totals),
            "uplift": dict(uplift),
            "daily": [dict(r) for r in daily],
            "uplift_timeseries": [dict(r) for r in uplift_ts],
        })

    @app.route("/api/organizations/<org_id>/remote-aggregate")
    def organization_remote_aggregate(org_id):
        """Return the cached aggregate from hub/git sync pull (org-wide stats from all members)."""
        with get_db() as db:
            cache_key = f"org_aggregate_{org_id}"
            cached = _get_config(db, cache_key)
        if not cached:
            return jsonify({"aggregate": None, "pulled_at": None})
        return jsonify({
            "aggregate": cached.get("aggregate"),
            "pulled_at": cached.get("pulled_at"),
        })

    # --- Org hub management (dashboard-facing, for local orgs) ---

    @app.route("/api/organizations/<org_id>/hub-info")
    def organization_hub_info(org_id):
        """Hub admin info: members, active invite codes, sharing config."""
        with get_db() as db:
            org = db.execute("SELECT * FROM organizations WHERE org_id = ?", (org_id,)).fetchone()
            if not org:
                return jsonify({"error": "not found"}), 404
            members = db.execute(
                "SELECT member_name, role, joined_at, last_push_at, api_key FROM hub_members WHERE org_id = ? ORDER BY joined_at",
                (org_id,),
            ).fetchall()
            invites = db.execute(
                "SELECT invite_code, created_by, created_at, revoked_at FROM hub_invites WHERE org_id = ? ORDER BY created_at DESC",
                (org_id,),
            ).fetchall()
            sharing_config = json.loads(org["sharing_config"]) if org["sharing_config"] else DEFAULT_SHARING_CONFIG

            # Get org folder paths for admin local stats
            folder_rows = db.execute(
                "SELECT folder_path FROM org_folders WHERE org_id = ?", (org_id,)
            ).fetchall()
            folder_paths = [f["folder_path"] for f in folder_rows]

            # Build member list with stats from hub_sessions + hub_aggregates
            member_list = []
            for m in members:
                md = {k: m[k] for k in ("member_name", "role", "joined_at", "last_push_at")}

                if m["role"] == "admin" and folder_paths:
                    # Admin: compute local stats from sessions in org folders
                    path_conds = " OR ".join(
                        ["(s.project_path = ? OR s.project_path LIKE ? || '/%')"] * len(folder_paths)
                    )
                    fp_params: list = []
                    for fp in folder_paths:
                        fp_params.extend([fp, fp])
                    local_count = db.execute(
                        f"SELECT COUNT(*) as c FROM sessions s WHERE COALESCE(s.is_local, 1) = 1 AND ({path_conds})",
                        fp_params,
                    ).fetchone()
                    md["sessions_pushed"] = local_count["c"] if local_count else 0
                    local_uplift = db.execute(
                        f"""SELECT ROUND(AVG(uo.uplift_factor), 2) as avg
                           FROM uplift_outputs uo
                           JOIN sessions s ON s.session_id = uo.session_id
                           WHERE uo.output_id = 'llm-judge'
                             AND COALESCE(s.is_local, 1) = 1
                             AND ({path_conds})""",
                        fp_params,
                    ).fetchone()
                    md["avg_uplift"] = local_uplift["avg"] if local_uplift and local_uplift["avg"] is not None else None
                    md["has_sessions"] = True  # admin sessions are local, always viewable
                    md["aggregate_only"] = False
                else:
                    # Non-admin members: use hub data
                    hub_sess = db.execute(
                        "SELECT COUNT(*) as c FROM hub_sessions WHERE org_id = ? AND member_name = ?",
                        (org_id, m["member_name"]),
                    ).fetchone()
                    hub_sess_count = hub_sess["c"] if hub_sess else 0
                    md["has_sessions"] = hub_sess_count > 0

                    member_agg = db.execute(
                        "SELECT aggregate_data FROM hub_aggregates WHERE org_id = ? AND member_name = ?",
                        (org_id, m["member_name"]),
                    ).fetchone()
                    agg_data = {}
                    if member_agg:
                        try:
                            agg_data = json.loads(member_agg["aggregate_data"]) if isinstance(member_agg["aggregate_data"], str) else member_agg["aggregate_data"]
                        except (json.JSONDecodeError, TypeError):
                            pass

                    md["sessions_pushed"] = hub_sess_count if hub_sess_count > 0 else agg_data.get("total_sessions", 0)
                    md["avg_uplift"] = round(agg_data["avg_uplift_factor"], 2) if agg_data.get("avg_uplift_factor") is not None else None
                    md["aggregate_only"] = hub_sess_count == 0 and md["sessions_pushed"] > 0

                member_list.append(md)
        return jsonify({
            "org_id": org_id,
            "org_name": org["name"],
            "sharing_config": sharing_config,
            "members": member_list,
            "invites": [dict(i) for i in invites],
        })

    @app.route("/api/organizations/<org_id>/sharing-config", methods=["PUT"])
    def update_sharing_config(org_id):
        """Update org sharing config from the detail page."""
        data = request.get_json()
        if not data or "sharing_config" not in data:
            return jsonify({"error": "sharing_config required"}), 400
        with get_db() as db:
            org = db.execute("SELECT 1 FROM organizations WHERE org_id = ?", (org_id,)).fetchone()
            if not org:
                return jsonify({"error": "not found"}), 404
            db.execute(
                "UPDATE organizations SET sharing_config = ? WHERE org_id = ?",
                (json.dumps(data["sharing_config"]), org_id),
            )
        return jsonify({"status": "updated"})

    @app.route("/api/organizations/<org_id>/hub-members/<member_name>", methods=["DELETE"])
    def organization_hub_member_delete(org_id, member_name):
        """Remove a member from the hub."""
        with get_db() as db:
            cursor = db.execute(
                "DELETE FROM hub_members WHERE org_id = ? AND member_name = ? AND role != 'admin'",
                (org_id, member_name),
            )
            if cursor.rowcount == 0:
                return jsonify({"error": "Member not found or is admin"}), 404
            # Also remove their sessions and aggregates
            db.execute("DELETE FROM hub_sessions WHERE org_id = ? AND member_name = ?", (org_id, member_name))
            db.execute("DELETE FROM hub_aggregates WHERE org_id = ? AND member_name = ?", (org_id, member_name))
        return jsonify({"status": "deleted"})

    @app.route("/api/organizations/<org_id>/hub-sessions")
    def organization_hub_sessions(org_id):
        """Return sessions from hub_sessions table for hub admins, optionally filtered by member."""
        member_filter = request.args.get("member", None, type=str)
        with get_db() as db:
            org = db.execute("SELECT 1 FROM organizations WHERE org_id = ?", (org_id,)).fetchone()
            if not org:
                return jsonify({"error": "not found"}), 404
            query = "SELECT * FROM hub_sessions WHERE org_id = ?"
            params: list = [org_id]
            if member_filter:
                query += " AND member_name = ?"
                params.append(member_filter)
            query += " ORDER BY pushed_at DESC"
            rows = db.execute(query, params).fetchall()
            sessions = []
            for row in rows:
                try:
                    data = json.loads(row["session_data"])
                    data["member_name"] = row["member_name"]
                    data["pushed_at"] = row["pushed_at"]
                    sessions.append(data)
                except (json.JSONDecodeError, TypeError):
                    continue
        return jsonify(sessions)

    @app.route("/api/organizations/<org_id>/uplift-by-member")
    def organization_uplift_by_member(org_id):
        """Return per-member uplift from hub_aggregates for bar chart."""
        with get_db() as db:
            rows = db.execute(
                "SELECT member_name, aggregate_data FROM hub_aggregates WHERE org_id = ?",
                (org_id,),
            ).fetchall()
            result = []
            for row in rows:
                try:
                    agg = json.loads(row["aggregate_data"]) if isinstance(row["aggregate_data"], str) else row["aggregate_data"]
                except (json.JSONDecodeError, TypeError):
                    continue
                if agg.get("avg_uplift_factor") is not None:
                    result.append({
                        "member_name": row["member_name"],
                        "avg_uplift": round(agg["avg_uplift_factor"], 2),
                        "sessions": agg.get("total_sessions", 0),
                    })
        return jsonify(result)

    @app.route("/api/organizations/<org_id>/unpushed-sessions")
    def organization_unpushed_sessions(org_id):
        """Return local sessions in org folders that have been added/updated since last push."""
        with get_db() as db:
            org = db.execute("SELECT * FROM organizations WHERE org_id = ?", (org_id,)).fetchone()
            if not org:
                return jsonify({"error": "not found"}), 404

            folder_paths = [
                r["folder_path"]
                for r in db.execute("SELECT folder_path FROM org_folders WHERE org_id = ?", (org_id,)).fetchall()
            ]
            if not folder_paths:
                return jsonify({"sessions": [], "total": 0, "last_push_at": None})

            membership_row = db.execute(
                "SELECT last_push_at FROM org_memberships WHERE org_id = ?", (org_id,)
            ).fetchone()
            last_push = membership_row["last_push_at"] if membership_row else None

            path_conds = " OR ".join(
                ["(s.project_path = ? OR s.project_path LIKE ? || '/%')"] * len(folder_paths)
            )
            path_params: list = []
            for fp in folder_paths:
                path_params.extend([fp, fp])

            where = f"WHERE COALESCE(s.is_local, 1) = 1 AND ({path_conds})"
            params: list = list(path_params)
            if last_push:
                where += " AND s.updated_at > ?"
                params.append(last_push)

            rows = db.execute(
                f"""SELECT s.session_id, s.project_name, s.model_primary, s.started_at,
                           s.ended_at, s.message_count, s.tool_call_count,
                           s.total_input_tokens + s.total_output_tokens as total_tokens,
                           s.total_cost_usd, s.updated_at,
                           uo.uplift_factor,
                           CASE WHEN EXISTS (
                               SELECT 1 FROM script_results sj
                               WHERE sj.session_id = s.session_id
                                 AND sj.script_id = 'llm-time-estimate'
                                 AND sj.status = 'completed'
                                 AND sj.session_message_count >= s.message_count
                           ) THEN 1 ELSE 0 END as judge_current
                    FROM sessions s
                    LEFT JOIN uplift_outputs uo ON s.session_id = uo.session_id AND uo.output_id = 'llm-judge'
                    {where}
                    ORDER BY s.updated_at DESC
                    LIMIT 50""",
                params,
            ).fetchall()

            total_row = db.execute(
                f"SELECT COUNT(*) as c FROM sessions s {where}", params
            ).fetchone()
            total = total_row["c"] if total_row else 0

            # Count unjudged (no judge script result) and stale (judged but session updated since)
            unjudged_row = db.execute(
                f"""SELECT COUNT(*) as c FROM sessions s
                    {where}
                    AND s.session_id NOT IN (
                        SELECT session_id FROM script_results
                        WHERE script_id = 'llm-time-estimate' AND status = 'completed'
                    )""",
                params,
            ).fetchone()
            unjudged_count = unjudged_row["c"] if unjudged_row else 0

            stale_row = db.execute(
                f"""SELECT COUNT(*) as c FROM sessions s
                    JOIN script_results sr ON s.session_id = sr.session_id
                        AND sr.script_id = 'llm-time-estimate' AND sr.status = 'completed'
                    {where}
                    AND sr.session_message_count IS NOT NULL
                    AND sr.session_message_count < s.message_count""",
                params,
            ).fetchone()
            stale_count = stale_row["c"] if stale_row else 0

        return jsonify({
            "sessions": [dict(r) for r in rows],
            "total": total,
            "last_push_at": last_push,
            "unjudged_count": unjudged_count,
            "stale_count": stale_count,
        })

    @app.route("/api/organizations/<org_id>/hub-invites", methods=["POST"])
    def organization_hub_invite_create(org_id):
        """Generate a new invite code for this org."""
        with get_db() as db:
            org = db.execute("SELECT 1 FROM organizations WHERE org_id = ?", (org_id,)).fetchone()
            if not org:
                return jsonify({"error": "not found"}), 404
            invite_code = secrets.token_urlsafe(16)
            now = datetime.now(timezone.utc).isoformat()
            db.execute(
                "INSERT INTO hub_invites (invite_code, org_id, created_at) VALUES (?, ?, ?)",
                (invite_code, org_id, now),
            )
        return jsonify({"invite_code": invite_code}), 201

    @app.route("/api/organizations/<org_id>/hub-invites/<invite_code>/revoke", methods=["POST"])
    def organization_hub_invite_revoke(org_id, invite_code):
        """Revoke an invite code."""
        with get_db() as db:
            now = datetime.now(timezone.utc).isoformat()
            cursor = db.execute(
                "UPDATE hub_invites SET revoked_at = ? WHERE invite_code = ? AND org_id = ? AND revoked_at IS NULL",
                (now, invite_code, org_id),
            )
            if cursor.rowcount == 0:
                return jsonify({"error": "invite not found or already revoked"}), 404
        return jsonify({"status": "revoked"})

    # --- Org membership endpoints ---

    @app.route("/api/org-memberships")
    def org_memberships_list():
        """List all org memberships (orgs this instance has joined as member).

        Returns: [{org_id, org_name, hub_url, ...}]
        """
        with get_db() as db:
            rows = db.execute("SELECT * FROM org_memberships ORDER BY org_name").fetchall()
        return jsonify([dict(r) for r in rows])

    @app.route("/api/org-memberships/join", methods=["POST"])
    def org_memberships_join():
        """Join a remote org hub using an invite code.

        Body: {hub_url, invite_code, name}
        Returns: membership result (201)
        """
        data = request.get_json(silent=True) or {}
        hub_url = data.get("hub_url", "")
        invite_code = data.get("invite_code", "")
        name = data.get("name", "")
        if not hub_url:
            return jsonify({"error": "hub_url required"}), 400
        if not invite_code:
            return jsonify({"error": "invite_code required"}), 400
        if not name:
            return jsonify({"error": "name required"}), 400
        from open_uplift.sync import join_org
        try:
            with get_db() as db:
                result = join_org(db, hub_url, invite_code, name)
        except Exception as e:
            return jsonify({"error": str(e)}), 400
        return jsonify(result), 201

    @app.route("/api/org-memberships/<org_id>/sync", methods=["POST"])
    def org_memberships_sync(org_id):
        """Full sync (push + pull) for an org membership.

        Returns: sync result dict
        """
        from open_uplift.sync import sync_org
        with get_db() as db:
            membership = db.execute(
                "SELECT * FROM org_memberships WHERE org_id = ?", (org_id,)
            ).fetchone()
            if not membership:
                return jsonify({"error": "membership not found"}), 404
            result = sync_org(db, dict(membership))
        return jsonify(result)

    @app.route("/api/org-memberships/<org_id>/push", methods=["POST"])
    def org_memberships_push(org_id):
        """Push local session data to the remote org hub.

        Returns: push result dict
        """
        from open_uplift.sync import push_org
        with get_db() as db:
            membership = db.execute(
                "SELECT * FROM org_memberships WHERE org_id = ?", (org_id,)
            ).fetchone()
            if not membership:
                return jsonify({"error": "membership not found"}), 404
            result = push_org(db, dict(membership))
        return jsonify(result)

    @app.route("/api/org-memberships/<org_id>/pull", methods=["POST"])
    def org_memberships_pull(org_id):
        """Pull aggregated data from the remote org hub.

        Returns: pull result dict
        """
        from open_uplift.sync import pull_org
        with get_db() as db:
            membership = db.execute(
                "SELECT * FROM org_memberships WHERE org_id = ?", (org_id,)
            ).fetchone()
            if not membership:
                return jsonify({"error": "membership not found"}), 404
            result = pull_org(db, dict(membership))
        return jsonify(result)

    @app.route("/api/org-memberships/<org_id>/pull-config", methods=["GET", "PUT"])
    def org_memberships_pull_config(org_id):
        """GET: retrieve pull config and sharing config. PUT: update pull config (clamped to sharing limits).

        PUT body: {pull_config: {...}}
        Returns: GET: {pull_config, sharing_config} / PUT: {status, pull_config}
        """
        with get_db() as db:
            membership = db.execute(
                "SELECT pull_config, sharing_config FROM org_memberships WHERE org_id = ?", (org_id,)
            ).fetchone()
            if not membership:
                return jsonify({"error": "membership not found"}), 404

            sharing = json.loads(membership["sharing_config"]) if membership["sharing_config"] else DEFAULT_SHARING_CONFIG

            if request.method == "GET":
                pull = json.loads(membership["pull_config"]) if membership["pull_config"] else None
                return jsonify({"pull_config": pull, "sharing_config": sharing})

            data = request.get_json()
            if not data or "pull_config" not in data:
                return jsonify({"error": "pull_config required"}), 400
            pc = data["pull_config"]
            # Clamp: member cannot pull more than what sharing_config offers
            sharing_stats = sharing.get("stats", {})
            for key in list(pc.get("stats", {}).keys()):
                if not sharing_stats.get(key):
                    pc["stats"][key] = False
            if pc.get("level", 1) > sharing.get("level", 1):
                pc["level"] = sharing["level"]
            db.execute(
                "UPDATE org_memberships SET pull_config = ? WHERE org_id = ?",
                (json.dumps(pc), org_id),
            )
        return jsonify({"status": "updated", "pull_config": pc})

    @app.route("/api/org-memberships/sync-all", methods=["POST"])
    def org_memberships_sync_all():
        """Sync all org memberships (push + pull for each).

        Returns: {results: [...]}
        """
        from open_uplift.sync import sync_all_orgs
        results = sync_all_orgs()
        return jsonify({"results": results})

    # --- Hub server endpoints (always registered, auth-gated) ---

    def _hub_auth(db):
        """Authenticate hub requests via Bearer token. Returns hub_member row or None."""
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        token = auth[7:]
        return db.execute(
            "SELECT * FROM hub_members WHERE api_key = ?", (token,)
        ).fetchone()

    def _filter_session_by_config(session_data, sharing_config):
        """Server-side enforcement of which fields get stored based on sharing_config."""
        if not sharing_config:
            sharing_config = DEFAULT_SHARING_CONFIG
        stats_config = sharing_config.get("stats", {})
        filtered = {
            "session_id": session_data.get("session_id"),
            "started_at": session_data.get("started_at"),
            "ended_at": session_data.get("ended_at"),
            "model_primary": session_data.get("model_primary"),
            "project_name": session_data.get("project_name"),
            "scaffold": session_data.get("scaffold"),
        }
        if stats_config.get("tokens"):
            for k in ("total_input_tokens", "total_output_tokens", "total_cache_read_tokens", "total_cache_create_tokens"):
                if k in session_data:
                    filtered[k] = session_data[k]
        if stats_config.get("cost") and "total_cost_usd" in session_data:
            filtered["total_cost_usd"] = session_data["total_cost_usd"]
        if stats_config.get("messages") and "message_count" in session_data:
            filtered["message_count"] = session_data["message_count"]
        if stats_config.get("tool_calls") and "tool_call_count" in session_data:
            filtered["tool_call_count"] = session_data["tool_call_count"]
        if stats_config.get("uplift") and "uplift_factor" in session_data:
            filtered["uplift_factor"] = session_data["uplift_factor"]
        return filtered

    def _combine_hub_aggregates(agg_rows):
        """Sum totals across hub_aggregates rows, average uplift, merge breakdowns."""
        totals = {
            "total_sessions": 0,
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "total_messages": 0,
            "total_tool_calls": 0,
            "member_count": len(agg_rows),
        }
        uplift_sum = 0.0
        uplift_count = 0
        all_uplift_values: list[float] = []
        scaffold_map: dict[str, dict] = {}  # scaffold -> {sum, count}
        model_map: dict[str, dict] = {}     # model -> {sum, count}
        for row in agg_rows:
            try:
                agg = json.loads(row["aggregate_data"]) if isinstance(row["aggregate_data"], str) else row["aggregate_data"]
            except (json.JSONDecodeError, TypeError):
                continue
            totals["total_sessions"] += agg.get("total_sessions", 0)
            totals["total_tokens"] += agg.get("total_tokens", 0)
            totals["total_cost_usd"] += agg.get("total_cost_usd", 0.0)
            totals["total_messages"] += agg.get("total_messages", 0)
            totals["total_tool_calls"] += agg.get("total_tool_calls", 0)
            if agg.get("avg_uplift_factor") is not None:
                uplift_sum += agg["avg_uplift_factor"]
                uplift_count += 1
            # Merge by_scaffold
            for entry in agg.get("by_scaffold", []):
                key = entry.get("scaffold", "unknown")
                cnt = entry.get("count", 0)
                avg = entry.get("avg_uplift", 0)
                if key not in scaffold_map:
                    scaffold_map[key] = {"sum": 0.0, "count": 0}
                scaffold_map[key]["sum"] += avg * cnt
                scaffold_map[key]["count"] += cnt
            # Merge by_model
            for entry in agg.get("by_model", []):
                key = entry.get("model", "unknown")
                cnt = entry.get("count", 0)
                avg = entry.get("avg_uplift", 0)
                if key not in model_map:
                    model_map[key] = {"sum": 0.0, "count": 0}
                model_map[key]["sum"] += avg * cnt
                model_map[key]["count"] += cnt
            # Concatenate uplift values
            all_uplift_values.extend(agg.get("uplift_values", []))
        totals["avg_uplift_factor"] = (uplift_sum / uplift_count) if uplift_count > 0 else None
        totals["by_scaffold"] = [
            {"scaffold": k, "avg_uplift": round(v["sum"] / v["count"], 2), "count": v["count"]}
            for k, v in scaffold_map.items() if v["count"] > 0
        ]
        totals["by_model"] = [
            {"model": k, "avg_uplift": round(v["sum"] / v["count"], 2), "count": v["count"]}
            for k, v in model_map.items() if v["count"] > 0
        ]
        totals["uplift_values"] = all_uplift_values
        return totals

    @app.route("/hub/join", methods=["POST"])
    def hub_join():
        """Join an org using an invite code. Returns API key."""
        data = request.get_json(silent=True) or {}
        invite_code = data.get("invite_code", "")
        member_name = data.get("member_name", "")
        if not invite_code or not member_name:
            return jsonify({"error": "invite_code and member_name required"}), 400

        with get_db() as db:
            invite = db.execute(
                "SELECT * FROM hub_invites WHERE invite_code = ? AND revoked_at IS NULL",
                (invite_code,),
            ).fetchone()
            if not invite:
                return jsonify({"error": "Invalid or revoked invite code"}), 403

            org_id = invite["org_id"]
            org = db.execute("SELECT * FROM organizations WHERE org_id = ?", (org_id,)).fetchone()
            if not org:
                return jsonify({"error": "Organization not found"}), 404

            # Check for existing member
            existing = db.execute(
                "SELECT * FROM hub_members WHERE org_id = ? AND member_name = ?",
                (org_id, member_name),
            ).fetchone()
            if existing:
                return jsonify({"error": f"Member '{member_name}' already exists in this org"}), 409

            api_key = secrets.token_urlsafe(32)
            now = datetime.now(timezone.utc).isoformat()
            db.execute(
                """INSERT INTO hub_members (org_id, member_name, api_key, role, joined_at)
                   VALUES (?, ?, ?, 'member', ?)""",
                (org_id, member_name, api_key, now),
            )

            sharing_config = json.loads(org["sharing_config"]) if org["sharing_config"] else DEFAULT_SHARING_CONFIG

        return jsonify({
            "org_id": org_id,
            "org_name": org["name"],
            "api_key": api_key,
            "sharing_config": sharing_config,
            "role": "member",
        }), 201

    @app.route("/hub/push", methods=["POST"])
    def hub_push():
        """Push aggregate + sessions to the hub."""
        with get_db() as db:
            member = _hub_auth(db)
            if not member:
                return jsonify({"error": "Unauthorized"}), 401

            data = request.get_json(silent=True) or {}
            org_id = member["org_id"]
            member_name = member["member_name"]
            now = datetime.now(timezone.utc).isoformat()

            # Get org sharing config for server-side enforcement
            org = db.execute("SELECT sharing_config FROM organizations WHERE org_id = ?", (org_id,)).fetchone()
            sharing_config = json.loads(org["sharing_config"]) if org and org["sharing_config"] else None

            # Store aggregate
            aggregate = data.get("aggregate", {})
            db.execute(
                """INSERT INTO hub_aggregates (org_id, member_name, aggregate_data, pushed_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(org_id, member_name) DO UPDATE SET
                       aggregate_data = excluded.aggregate_data,
                       pushed_at = excluded.pushed_at""",
                (org_id, member_name, json.dumps(aggregate), now),
            )

            # Store sessions (with server-side config enforcement)
            sessions = data.get("sessions", [])
            for sess in sessions:
                filtered = _filter_session_by_config(sess, sharing_config)
                session_id = filtered.get("session_id")
                if not session_id:
                    continue
                db.execute(
                    """INSERT INTO hub_sessions (org_id, member_name, session_id, session_data, pushed_at)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(org_id, session_id) DO UPDATE SET
                           session_data = excluded.session_data,
                           pushed_at = excluded.pushed_at""",
                    (org_id, member_name, session_id, json.dumps(filtered), now),
                )

            # Update member's last_push_at
            db.execute(
                "UPDATE hub_members SET last_push_at = ? WHERE member_id = ?",
                (now, member["member_id"]),
            )

        return jsonify({"status": "ok", "stored_sessions": len(sessions)})

    @app.route("/hub/pull")
    def hub_pull():
        """Pull aggregate + sessions from other members (including admin's local data)."""
        from open_uplift.sync import _gather_aggregate, _gather_sessions

        with get_db() as db:
            member = _hub_auth(db)
            if not member:
                return jsonify({"error": "Unauthorized"}), 401

            org_id = member["org_id"]
            member_name = member["member_name"]
            since = request.args.get("since")

            org = db.execute("SELECT * FROM organizations WHERE org_id = ?", (org_id,)).fetchone()
            sharing_config = json.loads(org["sharing_config"]) if org and org["sharing_config"] else DEFAULT_SHARING_CONFIG

            # Get aggregates from OTHER members (pushed data)
            agg_rows = db.execute(
                "SELECT * FROM hub_aggregates WHERE org_id = ? AND member_name != ?",
                (org_id, member_name),
            ).fetchall()

            # Also include admin's local aggregate (admin data lives in local
            # sessions, not hub_aggregates)
            admin = db.execute(
                "SELECT member_name FROM hub_members WHERE org_id = ? AND role = 'admin'",
                (org_id,),
            ).fetchone()
            admin_name = admin["member_name"] if admin else None
            all_agg_rows = list(agg_rows)
            if admin_name and admin_name != member_name:
                admin_agg = _gather_aggregate(db, sharing_config, org_id=org_id)
                if admin_agg:
                    all_agg_rows.append({"aggregate_data": json.dumps(admin_agg)})

            aggregate = _combine_hub_aggregates(all_agg_rows)

            # Get sessions from OTHER members (pushed data)
            sess_query = "SELECT * FROM hub_sessions WHERE org_id = ? AND member_name != ?"
            sess_params: list = [org_id, member_name]
            if since:
                sess_query += " AND pushed_at > ?"
                sess_params.append(since)
            sess_rows = db.execute(sess_query, sess_params).fetchall()
            sessions = []
            for row in sess_rows:
                try:
                    sess_data = json.loads(row["session_data"])
                    sess_data["member_name"] = row["member_name"]
                    sessions.append(sess_data)
                except (json.JSONDecodeError, TypeError):
                    continue

            # Also include admin's local sessions if sharing level >= 2
            if admin_name and admin_name != member_name and sharing_config.get("level", 1) >= 2:
                admin_sessions = _gather_sessions(db, sharing_config, since, org_id=org_id)
                for s in admin_sessions:
                    s["member_name"] = admin_name
                sessions.extend(admin_sessions)

            # Member list
            members = db.execute(
                "SELECT member_name, last_push_at FROM hub_members WHERE org_id = ?",
                (org_id,),
            ).fetchall()
            member_list = [{"member_name": m["member_name"], "pushed_at": m["last_push_at"]} for m in members]

        return jsonify({
            "org_name": org["name"] if org else "",
            "sharing_config": sharing_config,
            "aggregate": aggregate,
            "sessions": sessions,
            "member_count": len(member_list),
            "members": member_list,
        })

    @app.route("/hub/members")
    def hub_members_list():
        """List org members."""
        with get_db() as db:
            member = _hub_auth(db)
            if not member:
                return jsonify({"error": "Unauthorized"}), 401
            rows = db.execute(
                "SELECT member_name, role, joined_at, last_push_at FROM hub_members WHERE org_id = ?",
                (member["org_id"],),
            ).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.route("/hub/invite", methods=["POST"])
    def hub_invite_create():
        """Generate a reusable invite code (admin only)."""
        with get_db() as db:
            member = _hub_auth(db)
            if not member:
                return jsonify({"error": "Unauthorized"}), 401
            if member["role"] != "admin":
                return jsonify({"error": "Admin role required"}), 403

            invite_code = secrets.token_urlsafe(16)
            now = datetime.now(timezone.utc).isoformat()
            db.execute(
                "INSERT INTO hub_invites (invite_code, org_id, created_by, created_at) VALUES (?, ?, ?, ?)",
                (invite_code, member["org_id"], member["member_name"], now),
            )
        return jsonify({"invite_code": invite_code}), 201

    @app.route("/hub/invite/revoke", methods=["POST"])
    def hub_invite_revoke():
        """Revoke an invite code (admin only)."""
        with get_db() as db:
            member = _hub_auth(db)
            if not member:
                return jsonify({"error": "Unauthorized"}), 401
            if member["role"] != "admin":
                return jsonify({"error": "Admin role required"}), 403

            data = request.get_json(silent=True) or {}
            invite_code = data.get("invite_code", "")
            if not invite_code:
                return jsonify({"error": "invite_code required"}), 400

            now = datetime.now(timezone.utc).isoformat()
            cursor = db.execute(
                "UPDATE hub_invites SET revoked_at = ? WHERE invite_code = ? AND org_id = ? AND revoked_at IS NULL",
                (now, invite_code, member["org_id"]),
            )
            if cursor.rowcount == 0:
                return jsonify({"error": "Invite not found or already revoked"}), 404
        return jsonify({"status": "revoked"})

    @app.route("/hub/config", methods=["GET", "PUT"])
    def hub_config():
        """Get or update org sharing config."""
        with get_db() as db:
            member = _hub_auth(db)
            if not member:
                return jsonify({"error": "Unauthorized"}), 401

            org_id = member["org_id"]

            if request.method == "GET":
                org = db.execute("SELECT * FROM organizations WHERE org_id = ?", (org_id,)).fetchone()
                sharing_config = json.loads(org["sharing_config"]) if org and org["sharing_config"] else DEFAULT_SHARING_CONFIG
                return jsonify({"org_id": org_id, "org_name": org["name"] if org else "", "sharing_config": sharing_config})

            # PUT — admin only
            if member["role"] != "admin":
                return jsonify({"error": "Admin role required"}), 403

            data = request.get_json(silent=True) or {}
            new_config = data.get("sharing_config")
            if not new_config:
                return jsonify({"error": "sharing_config required"}), 400

            db.execute(
                "UPDATE organizations SET sharing_config = ? WHERE org_id = ?",
                (json.dumps(new_config), org_id),
            )
        return jsonify({"status": "updated", "sharing_config": new_config})

    # --- Start background workers ---
    start_worker()
    start_scheduler()
    from open_uplift.job_queue import start_sync_scheduler
    start_sync_scheduler()

    # --- Static file serving (React dashboard) ---

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_dashboard(path):
        """Serve the React dashboard SPA, falling back to index.html for client routes."""
        dist = str(DASHBOARD_DIR)
        if path and (DASHBOARD_DIR / path).is_file():
            return send_from_directory(dist, path)
        index = DASHBOARD_DIR / "index.html"
        if index.is_file():
            return send_from_directory(dist, "index.html")
        return jsonify({
            "message": "Dashboard not built yet. Run: cd dashboard && npm install && npm run build"
        }), 404

    return app
