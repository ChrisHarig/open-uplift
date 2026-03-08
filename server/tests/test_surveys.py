"""Tests for the survey system."""

import json

import pytest

from open_uplift.surveys import (
    DEFAULT_QUESTIONS,
    DEFAULT_SURVEYS,
    compute_outputs,
    get_active_survey,
    get_active_survey_id,
    get_questions,
    get_surveys,
    submit_survey_response,
)


def test_get_active_survey(db):
    survey = get_active_survey(db)
    assert survey["id"] == "default"
    assert len(survey["questions"]) >= 2
    # Questions should be resolved (dicts, not just IDs)
    assert isinstance(survey["questions"][0], dict)
    assert "label" in survey["questions"][0]


def test_get_active_survey_id(db):
    sid = get_active_survey_id(db)
    assert sid == "default"


def test_get_surveys(db):
    surveys = get_surveys(db)
    assert "default" in surveys


def test_get_questions(db):
    questions = get_questions(db)
    assert "human-est" in questions
    assert "llm-judge-trans" in questions


def test_question_structure(db):
    questions = get_questions(db)
    for qid, q in questions.items():
        assert "id" in q
        assert "type" in q
        assert "label" in q
        assert q["id"] == qid


def test_submit_survey_response(db, sample_session):
    response_id, outputs = submit_survey_response(
        db, sample_session, "default",
        answers={"human-est": 3.5},
        notes="Test response",
    )
    assert response_id > 0
    assert len(outputs) == 1
    assert outputs[0]["output_id"] == "human-est"
    assert outputs[0]["uplift_factor"] == 3.5


def test_submit_duplicate_prevention(db, sample_session):
    submit_survey_response(db, sample_session, "default", answers={"human-est": 2.0})
    with pytest.raises(ValueError, match="already exists"):
        submit_survey_response(db, sample_session, "default", answers={"human-est": 3.0})


def test_compute_outputs_human_est():
    survey_def = DEFAULT_SURVEYS["default"]
    outputs = compute_outputs(survey_def, {"human-est": 5.0})
    assert any(o["output_id"] == "human-est" for o in outputs)
    human_est = next(o for o in outputs if o["output_id"] == "human-est")
    assert human_est["uplift_factor"] == 5.0


def test_compute_outputs_llm_judge_trans():
    survey_def = DEFAULT_SURVEYS["default"]
    script_results = {
        "llm-time-estimate": {"minutes": 30},
    }
    outputs = compute_outputs(
        survey_def,
        {"llm-judge-trans": 120},  # 120 min without AI
        script_results,
    )
    llm_output = next(o for o in outputs if o["output_id"] == "llm-judge-trans")
    assert llm_output["uplift_factor"] == 4.0  # 120/30


def test_compute_outputs_llm_judge_no_scripts():
    survey_def = DEFAULT_SURVEYS["default"]
    outputs = compute_outputs(survey_def, {"llm-judge-trans": 120}, None)
    # Without script results, llm-judge-trans calculator should return None
    llm_outputs = [o for o in outputs if o["output_id"] == "llm-judge-trans"]
    assert len(llm_outputs) == 0


def test_survey_response_stored_in_db(db, sample_session):
    submit_survey_response(db, sample_session, "default", answers={"human-est": 2.5})

    row = db.execute(
        "SELECT * FROM survey_responses WHERE session_id = ?", (sample_session,)
    ).fetchone()
    assert row is not None
    assert json.loads(row["answers"]) == {"human-est": 2.5}


def test_uplift_output_stored_in_db(db, sample_session):
    submit_survey_response(db, sample_session, "default", answers={"human-est": 4.0})

    row = db.execute(
        "SELECT * FROM uplift_outputs WHERE output_id = 'human-est'"
    ).fetchone()
    assert row is not None
    assert row["uplift_factor"] == 4.0


def test_legacy_self_report_created(db, sample_session):
    """submit_survey_response also inserts into legacy self_reports table."""
    submit_survey_response(db, sample_session, "default", answers={"human-est": 3.0})

    row = db.execute(
        "SELECT * FROM self_reports WHERE session_id = ?", (sample_session,)
    ).fetchone()
    assert row is not None
    assert row["speedup_factor"] == 3.0
