"""Questions, surveys, and uplift output management."""

import json
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any


def slugify(text: str) -> str:
    """Convert text to a URL-friendly slug for use as an ID."""
    s = text.strip().lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s-]+", "-", s)
    return s.strip("-")

# --- Default question definitions ---

DEFAULT_QUESTIONS: dict[str, dict] = {
    "human-est": {
        "id": "human-est",
        "label": "How much faster did AI make you?",
        "description": (
            "Enter a speedup factor (e.g. 2x, 3.5x, 0.5x). "
            "If AI slowed you down to half speed, enter 0.5. "
            "Values can have up to two decimal places."
        ),
        "type": "number",
        "validation": {"min": 0.1, "max": 10000, "type": "number", "max_decimals": 2},
        "suffix": "x",
        "placeholder": "",
        "required": True,
    },
    "llm-judge-trans": {
        "id": "llm-judge-trans",
        "label": "How long would this have taken WITHOUT any AI usage?",
        "description": (
            "Estimate the total time in minutes for the tasks completed in this session, "
            "if done entirely without AI. Values can have up to two decimal places."
        ),
        "type": "number",
        "validation": {"min": 1, "max": 10000, "type": "number", "max_decimals": 2},
        "suffix": "min",
        "placeholder": "",
        "required": True,
    },
}

# --- Default survey definitions ---

DEFAULT_SURVEYS: dict[str, dict] = {
    "default": {
        "id": "default",
        "name": "Default",
        "description": "Self-reported speedup factor and counterfactual time estimate",
        "questions": ["human-est", "llm-judge-trans"],
        "scripts": [
            {
                "id": "transcript-compact",
                "name": "Compact transcript",
                "command": "open-uplift run-script transcript-compact --session-id {session_id}",
                "description": "Compacts the session transcript for LLM analysis",
                "required": False,
            },
            {
                "id": "llm-time-estimate",
                "name": "LLM time estimate",
                "command": "open-uplift run-script llm-time-estimate --session-id {session_id}",
                "description": "LLM analyzes transcript to estimate time-with-AI",
                "required": False,
            },
        ],
        "outputs": [
            {
                "id": "human-est",
                "name": "Human-estimated uplift",
                "description": "Uplift = speedup factor as reported by the human",
            },
            {
                "id": "llm-judge-trans",
                "name": "LLM-judge transcript uplift",
                "description": "Uplift = (human estimated time without AI) / (LLM-measured time with AI)",
            },
        ],
    },
}

DEFAULT_ACTIVE_SURVEY = "default"

# --- Output calculators ---
# Each takes (answers_dict, script_results_dict_or_None) and returns a float or None

OUTPUT_CALCULATORS: dict[str, Any] = {
    "human-est": lambda answers, _scripts: answers.get("human-est"),
    "llm-judge-trans": lambda answers, scripts: (
        answers.get("llm-judge-trans", 0)
        / scripts["llm-time-estimate"]["minutes"]
        if scripts and scripts.get("llm-time-estimate", {}).get("minutes")
        else None
    ),
}


# --- Config access ---


def _get_config(db: sqlite3.Connection, key: str) -> Any:
    row = db.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
    if row is None:
        return None
    return json.loads(row["value"])


def _set_config(db: sqlite3.Connection, key: str, value: Any) -> None:
    db.execute(
        "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
        (key, json.dumps(value)),
    )


def get_questions(db: sqlite3.Connection) -> dict[str, dict]:
    return _get_config(db, "questions") or {}


def get_surveys(db: sqlite3.Connection) -> dict[str, dict]:
    return _get_config(db, "surveys") or {}


def get_active_survey_id(db: sqlite3.Connection) -> str:
    return _get_config(db, "active_survey") or DEFAULT_ACTIVE_SURVEY


def get_active_survey(db: sqlite3.Connection) -> dict:
    """Return the active survey definition with question definitions resolved inline."""
    survey_id = get_active_survey_id(db)
    surveys = get_surveys(db)
    survey = surveys.get(survey_id)
    if survey is None:
        raise ValueError(f"Active survey '{survey_id}' not found")

    questions = get_questions(db)
    resolved = dict(survey)
    resolved["questions"] = [
        questions[qid] for qid in survey["questions"] if qid in questions
    ]
    return resolved


def delete_survey_response(db: sqlite3.Connection, session_id: str, survey_id: str) -> bool:
    """Delete a survey response and its uplift outputs. Returns True if deleted."""
    resp = db.execute(
        "SELECT id FROM survey_responses WHERE session_id = ? AND survey_id = ?",
        (session_id, survey_id),
    ).fetchone()
    if not resp:
        return False
    db.execute("DELETE FROM uplift_outputs WHERE survey_response_id = ?", (resp["id"],))
    db.execute("DELETE FROM survey_responses WHERE id = ?", (resp["id"],))
    return True


def set_active_survey(db: sqlite3.Connection, survey_id: str) -> None:
    surveys = get_surveys(db)
    if survey_id not in surveys:
        raise ValueError(f"Survey '{survey_id}' not found. Available: {list(surveys.keys())}")
    _set_config(db, "active_survey", survey_id)


def add_question(db: sqlite3.Connection, question: dict) -> None:
    questions = get_questions(db)
    questions[question["id"]] = question
    _set_config(db, "questions", questions)


def add_survey(db: sqlite3.Connection, survey: dict) -> None:
    surveys = get_surveys(db)
    surveys[survey["id"]] = survey
    _set_config(db, "surveys", surveys)


# --- Response submission ---


def submit_survey_response(
    db: sqlite3.Connection,
    session_id: str,
    survey_id: str,
    answers: dict[str, float],
    notes: str = "",
) -> tuple[int, list[dict]]:
    """Insert a survey response and compute outputs.

    Returns (response_id, list_of_output_dicts).
    """
    now = datetime.now(timezone.utc).isoformat()

    # Check for duplicate
    existing = db.execute(
        "SELECT id FROM survey_responses WHERE session_id = ? AND survey_id = ?",
        (session_id, survey_id),
    ).fetchone()
    if existing:
        raise ValueError(f"Report already exists for session {session_id}")

    db.execute(
        """INSERT INTO survey_responses
           (session_id, survey_id, tool_source, timestamp, answers, notes)
           VALUES (?, ?, 'claude_code', ?, ?, ?)""",
        (session_id, survey_id, now, json.dumps(answers), notes),
    )
    response_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Load script results for this session so judge outputs can be computed
    script_results_rows = db.execute(
        "SELECT script_id, result FROM script_results WHERE session_id = ? AND status = 'completed'",
        (session_id,),
    ).fetchall()
    script_results: dict | None = None
    if script_results_rows:
        script_results = {}
        for row in script_results_rows:
            if row["result"]:
                script_results[row["script_id"]] = json.loads(row["result"])

    # Compute and store outputs
    surveys = get_surveys(db)
    survey_def = surveys.get(survey_id, {})
    outputs = compute_outputs(survey_def, answers, script_results)

    for out in outputs:
        db.execute(
            """INSERT INTO uplift_outputs
               (session_id, survey_response_id, output_id, uplift_factor, metadata, timestamp)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (session_id, response_id, out["output_id"], out["uplift_factor"], json.dumps(out.get("metadata", {})), now),
        )

    return response_id, outputs


def compute_outputs(
    survey_def: dict,
    answers: dict[str, float],
    script_results: dict | None = None,
) -> list[dict]:
    """Calculate uplift outputs for a survey response."""
    results = []
    for output_def in survey_def.get("outputs", []):
        output_id = output_def["id"]
        calculator = OUTPUT_CALCULATORS.get(output_id)
        if calculator is None:
            continue
        try:
            value = calculator(answers, script_results)
        except Exception:
            value = None
        if value is not None:
            results.append({
                "output_id": output_id,
                "uplift_factor": round(float(value), 2),
                "metadata": {},
            })
    return results


# --- Seeding and migration helpers (called from db.py) ---


def seed_default_config(db: sqlite3.Connection) -> None:
    """Insert default questions and surveys. Merges with existing data."""
    # Merge default questions into existing (don't overwrite user additions)
    existing_questions = _get_config(db, "questions") or {}
    for qid, qdef in DEFAULT_QUESTIONS.items():
        if qid not in existing_questions:
            existing_questions[qid] = qdef
    _set_config(db, "questions", existing_questions)

    # Merge default surveys into existing
    existing_surveys = _get_config(db, "surveys") or {}
    for sid, sdef in DEFAULT_SURVEYS.items():
        if sid not in existing_surveys:
            existing_surveys[sid] = sdef
    _set_config(db, "surveys", existing_surveys)

    if _get_config(db, "active_survey") is None:
        _set_config(db, "active_survey", DEFAULT_ACTIVE_SURVEY)


