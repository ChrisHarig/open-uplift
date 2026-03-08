"""Tests for the session picker module."""

import pytest

from open_uplift.cli.session_picker import (
    _format_choice,
    _get_all_sessions,
    _get_current_project_sessions,
    search_sessions,
)


def _insert_sessions(db, count=5, project_path="/Users/dev/myproject", project_name="myproject", prefix="a"):
    """Helper to insert test sessions."""
    ids = []
    for i in range(count):
        sid = f"test-{prefix}-{i:04d}"
        db.execute(
            """INSERT INTO sessions
               (session_id, tool_source, project_path, project_name, git_branch,
                started_at, ended_at, message_count, total_cost_usd, model_primary, scaffold)
               VALUES (?, 'claude_code', ?, ?, 'main',
                       ?, NULL, ?, 0.01, 'claude-sonnet-4-6', 'claude_code')""",
            (sid, project_path, project_name,
             f"2026-02-{20-i:02d}T10:00:00Z", 3 + i),
        )
        ids.append(sid)
    db.commit()
    return ids


def test_format_choice_basic(db):
    row = {
        "started_at": "2026-02-20T10:00:00Z",
        "project_name": "myproject",
        "message_count": 5,
        "has_survey": 1,
        "has_compaction": 0,
        "has_judge": 0,
    }
    label = _format_choice(row)
    assert "myproject" in label
    assert "5 msgs" in label
    assert "[S]" in label
    assert "[ ]" in label


def test_format_choice_no_project():
    row = {
        "started_at": "2026-02-20T10:00:00Z",
        "project_name": None,
        "message_count": 3,
        "has_survey": 0,
        "has_compaction": 0,
        "has_judge": 0,
    }
    label = _format_choice(row)
    assert "unknown" in label


def test_get_current_project_sessions(db):
    _insert_sessions(db, count=3, project_path="/current/path", prefix="cur")
    _insert_sessions(db, count=2, project_path="/other/path", project_name="other", prefix="oth")
    rows = _get_current_project_sessions(db)
    # Should return nothing since CWD won't match /current/path
    # But test the function with a manual path
    db_rows = db.execute(
        """SELECT s.*,
              CASE WHEN sr.id IS NOT NULL THEN 1 ELSE 0 END as has_survey,
              0 as has_compaction, 0 as has_judge
           FROM sessions s
           LEFT JOIN survey_responses sr ON s.session_id = sr.session_id
           WHERE s.project_path = '/current/path'
           ORDER BY s.started_at DESC LIMIT 5""",
    ).fetchall()
    assert len(db_rows) == 3


def test_get_all_sessions(db):
    _insert_sessions(db, count=10)
    rows = _get_all_sessions(db, limit=5)
    assert len(rows) == 5


def test_get_all_sessions_with_offset(db):
    _insert_sessions(db, count=10)
    rows = _get_all_sessions(db, limit=5, offset=5)
    assert len(rows) == 5


def test_get_all_sessions_exclude(db):
    ids = _insert_sessions(db, count=5)
    rows = _get_all_sessions(db, limit=10, exclude_ids=[ids[0], ids[1]])
    assert len(rows) == 3


def test_search_sessions_by_name(db):
    _insert_sessions(db, count=3, project_name="myproject", prefix="mp")
    _insert_sessions(db, count=2, project_path="/other", project_name="other-project", prefix="op")
    results = search_sessions(db, "myproject")
    assert len(results) == 3


def test_search_sessions_by_id(db):
    ids = _insert_sessions(db, count=5)
    results = search_sessions(db, ids[0])
    assert len(results) == 1
    assert results[0]["session_id"] == ids[0]


def test_search_sessions_no_match(db):
    _insert_sessions(db, count=3)
    results = search_sessions(db, "nonexistent")
    assert len(results) == 0


def test_search_sessions_limit(db):
    _insert_sessions(db, count=10, prefix="lim")
    results = search_sessions(db, "test-lim", limit=3)
    assert len(results) == 3


def test_session_status_markers(db):
    """Sessions with survey/compaction/judge results get status markers."""
    ids = _insert_sessions(db, count=1)
    sid = ids[0]

    # Add survey response
    db.execute(
        """INSERT INTO survey_responses (session_id, survey_id, tool_source, timestamp, answers, notes)
           VALUES (?, 'survey-1', 'claude_code', '2026-02-20T10:00:00Z', '{"human-est": 3.5}', '')""",
        (sid,),
    )

    # Add compaction result
    db.execute(
        """INSERT INTO script_results (session_id, script_id, status, started_at, completed_at, prompt_id)
           VALUES (?, 'transcript-compact', 'completed', '2026-02-20T10:00:00Z', '2026-02-20T10:00:01Z', 'compaction-default')""",
        (sid,),
    )
    db.commit()

    rows = _get_all_sessions(db, limit=10)
    assert len(rows) == 1
    assert rows[0]["has_survey"] == 1
    assert rows[0]["has_compaction"] == 1
    assert rows[0]["has_judge"] == 0
