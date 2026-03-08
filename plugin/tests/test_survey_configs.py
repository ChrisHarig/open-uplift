"""Validate default survey configuration integrity."""

import json
import sqlite3
from pathlib import Path

import pytest

from open_uplift.surveys import (
    DEFAULT_QUESTIONS,
    DEFAULT_SURVEYS,
    OUTPUT_CALCULATORS,
    get_active_survey,
    submit_survey_response,
)


def test_default_questions_structure():
    for qid, q in DEFAULT_QUESTIONS.items():
        assert q["id"] == qid, f"Question {qid}: id mismatch"
        assert "type" in q, f"Question {qid}: missing 'type'"
        assert "label" in q, f"Question {qid}: missing 'label'"
        assert isinstance(q["label"], str), f"Question {qid}: label must be string"
        assert len(q["label"]) > 0, f"Question {qid}: label must not be empty"


def test_default_questions_validation():
    for qid, q in DEFAULT_QUESTIONS.items():
        if q["type"] == "number":
            val = q.get("validation", {})
            assert "min" in val, f"Question {qid}: number type needs min"
            assert "max" in val, f"Question {qid}: number type needs max"
            assert val["min"] < val["max"], f"Question {qid}: min must be < max"


def test_default_surveys_structure():
    for sid, s in DEFAULT_SURVEYS.items():
        assert s["id"] == sid, f"Survey {sid}: id mismatch"
        assert "questions" in s, f"Survey {sid}: missing 'questions'"
        assert isinstance(s["questions"], list), f"Survey {sid}: questions must be list"
        assert len(s["questions"]) >= 1, f"Survey {sid}: must have at least one question"


def test_survey_questions_reference_valid_questions():
    for sid, s in DEFAULT_SURVEYS.items():
        for qid in s["questions"]:
            assert qid in DEFAULT_QUESTIONS, (
                f"Survey {sid} references unknown question '{qid}'"
            )


def test_survey_outputs_structure():
    for sid, s in DEFAULT_SURVEYS.items():
        outputs = s.get("outputs", [])
        for output in outputs:
            assert "id" in output, f"Survey {sid}: output missing 'id'"
            assert "name" in output, f"Survey {sid}: output missing 'name'"


def test_output_calculators_exist():
    for sid, s in DEFAULT_SURVEYS.items():
        for output in s.get("outputs", []):
            assert output["id"] in OUTPUT_CALCULATORS, (
                f"Survey {sid}: output '{output['id']}' has no calculator"
            )


def test_custom_survey_creation(db):
    """Create a custom survey with custom questions, verify retrieval and submission."""
    from open_uplift.surveys import add_question, add_survey, get_surveys, get_questions, set_active_survey

    # Add custom question
    add_question(db, {
        "id": "custom-q",
        "label": "Custom question",
        "type": "number",
        "validation": {"min": 0, "max": 100, "type": "number"},
        "suffix": "",
        "required": True,
    })
    db.commit()

    questions = get_questions(db)
    assert "custom-q" in questions

    # Add custom survey
    add_survey(db, {
        "id": "custom-survey",
        "name": "custom-survey",
        "description": "Test survey",
        "questions": ["custom-q"],
        "scripts": [],
        "outputs": [],
    })
    db.commit()

    surveys = get_surveys(db)
    assert "custom-survey" in surveys

    # Set as active
    set_active_survey(db, "custom-survey")
    db.commit()

    active = get_active_survey(db)
    assert active["id"] == "custom-survey"
    assert len(active["questions"]) == 1
    assert active["questions"][0]["id"] == "custom-q"

    # Submit a response to the custom survey
    # First need a session
    db.execute(
        """INSERT INTO sessions
           (session_id, tool_source, started_at, message_count, scaffold)
           VALUES ('custom-sess', 'claude_code', '2026-01-01', 1, 'claude_code')""",
    )
    db.commit()

    response_id, outputs = submit_survey_response(
        db, "custom-sess", "custom-survey", {"custom-q": 42.0}
    )
    assert response_id > 0
    # No outputs expected since no calculators for custom output ids
    assert outputs == []
