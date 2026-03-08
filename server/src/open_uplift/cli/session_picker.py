"""Enhanced session picker with grouping, status markers, search, and pagination."""

import os
import sqlite3

import questionary

from open_uplift.cli.formatting import status_markers

PAGE_SIZE = 5

_SESSION_STATUS_SQL = """
SELECT s.*,
  CASE WHEN sr.id IS NOT NULL THEN 1 ELSE 0 END as has_survey,
  CASE WHEN sc.id IS NOT NULL THEN 1 ELSE 0 END as has_compaction,
  CASE WHEN sj.id IS NOT NULL THEN 1 ELSE 0 END as has_judge,
  CASE WHEN sj.id IS NOT NULL AND sj.session_message_count IS NOT NULL
       AND sj.session_message_count < s.message_count THEN 1 ELSE 0 END as judge_stale,
  uo.uplift_factor as uplift_factor
FROM sessions s
LEFT JOIN survey_responses sr ON s.session_id = sr.session_id
LEFT JOIN script_results sc ON s.session_id = sc.session_id AND sc.script_id = 'transcript-compact' AND sc.status = 'completed'
LEFT JOIN script_results sj ON s.session_id = sj.session_id AND sj.script_id = 'llm-time-estimate' AND sj.status = 'completed'
LEFT JOIN uplift_outputs uo ON s.session_id = uo.session_id AND uo.output_id = 'llm-judge'
"""


def _format_choice(row: dict) -> str:
    """Format a session row as a choice label."""
    date_str = (row.get("started_at") or "")[:16].replace("T", " ")
    project = row.get("project_name") or "unknown"
    msgs = row.get("message_count", 0)
    markers = status_markers(
        bool(row.get("has_survey")),
        bool(row.get("has_compaction")),
        bool(row.get("has_judge")),
        bool(row.get("judge_stale")),
    )
    return f"{date_str}  {project}  ({msgs} msgs) {markers}"


def _get_current_project_sessions(db: sqlite3.Connection, limit: int = PAGE_SIZE) -> list[dict]:
    """Get sessions matching the current working directory."""
    cwd = os.getcwd()
    rows = db.execute(
        _SESSION_STATUS_SQL + " WHERE s.project_path = ? ORDER BY s.started_at DESC LIMIT ?",
        (cwd, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def _get_all_sessions(db: sqlite3.Connection, limit: int = PAGE_SIZE, offset: int = 0, exclude_ids: list[str] | None = None) -> list[dict]:
    """Get all sessions with optional exclusion."""
    if exclude_ids:
        placeholders = ",".join("?" * len(exclude_ids))
        rows = db.execute(
            _SESSION_STATUS_SQL + f" WHERE s.session_id NOT IN ({placeholders}) ORDER BY s.started_at DESC LIMIT ? OFFSET ?",
            (*exclude_ids, limit, offset),
        ).fetchall()
    else:
        rows = db.execute(
            _SESSION_STATUS_SQL + " ORDER BY s.started_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    return [dict(r) for r in rows]


def search_sessions(db: sqlite3.Connection, keyword: str, limit: int = 20) -> list[dict]:
    """Search sessions by project name or session ID."""
    pattern = f"%{keyword}%"
    rows = db.execute(
        _SESSION_STATUS_SQL + " WHERE s.project_name LIKE ? OR s.session_id LIKE ? ORDER BY s.started_at DESC LIMIT ?",
        (pattern, pattern, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def pick_session(db: sqlite3.Connection, current_project: str | None = None) -> str | None:
    """Interactive session picker with grouping, search, and pagination.

    Groups sessions: "Current Project" (matching cwd) then "All Projects".
    Supports "Search..." and "Show more..." options.
    """
    cwd = current_project or os.getcwd()
    offset = 0

    while True:
        choices = []

        # Current project sessions
        current_rows = db.execute(
            _SESSION_STATUS_SQL + " WHERE s.project_path = ? ORDER BY s.started_at DESC LIMIT ?",
            (cwd, PAGE_SIZE),
        ).fetchall()
        current_rows = [dict(r) for r in current_rows]

        if current_rows:
            choices.append(questionary.Separator("── Current Project ──"))
            current_ids = []
            for r in current_rows:
                choices.append(questionary.Choice(title=_format_choice(r), value=r["session_id"]))
                current_ids.append(r["session_id"])
        else:
            current_ids = []

        # All projects sessions (excluding current project ones)
        all_rows = _get_all_sessions(db, limit=PAGE_SIZE, offset=offset, exclude_ids=current_ids if current_ids else None)
        if all_rows:
            choices.append(questionary.Separator("── All Projects ──"))
            for r in all_rows:
                choices.append(questionary.Choice(title=_format_choice(r), value=r["session_id"]))

        if not current_rows and not all_rows:
            return None

        # Action options
        choices.append(questionary.Separator("──────────────"))
        choices.append(questionary.Choice(title="Search...", value="__search__"))

        # Check if there are more sessions
        total = db.execute("SELECT COUNT(*) as cnt FROM sessions").fetchone()["cnt"]
        shown = len(current_rows) + len(all_rows) + offset
        if shown < total:
            choices.append(questionary.Choice(title="Show more...", value="__more__"))

        result = questionary.select("Select a session:", choices=choices).ask()

        if result is None:
            return None
        elif result == "__search__":
            keyword = questionary.text("Search (project name or session ID):").ask()
            if not keyword:
                continue
            search_results = search_sessions(db, keyword)
            if not search_results:
                questionary.print("No sessions found.", style="bold italic")
                continue
            search_choices = [
                questionary.Choice(title=_format_choice(r), value=r["session_id"])
                for r in search_results
            ]
            picked = questionary.select("Search results:", choices=search_choices).ask()
            if picked:
                return picked
        elif result == "__more__":
            offset += PAGE_SIZE
        else:
            return result
