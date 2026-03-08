import signal
import sys

import questionary

from open_uplift.db import get_db, init_db
from open_uplift.surveys import delete_survey_response, get_active_survey, submit_survey_response


def _handle_sigint(sig, frame):
    print("\nSurvey skipped.")
    sys.exit(0)


def _validate_number(val: str, validation: dict) -> bool | str:
    # Strip trailing "x", "min", etc. so users can type "3.5x"
    cleaned = val.strip().rstrip("xXmMin").strip()
    if not cleaned:
        return "Please enter a number"
    try:
        f = float(cleaned)
    except ValueError:
        return "Must be a number"
    lo = validation.get("min", 0)
    hi = validation.get("max", 10000)
    if not (lo <= f <= hi):
        return f"Must be between {lo} and {hi}"
    max_decimals = validation.get("max_decimals", 1)
    if "." in cleaned:
        decimal_part = cleaned.split(".")[1]
        if len(decimal_part) > max_decimals:
            return f"At most {max_decimals} decimal place(s)"
    return True


def _parse_number_input(val: str) -> float:
    """Parse a number input, stripping any suffix like 'x' or 'min'."""
    return float(val.strip().rstrip("xXmMin").strip())


def _ask_question(question: dict):
    """Render a single question in the terminal based on its definition."""
    if question.get("description"):
        print(f"  {question['description']}\n")

    if question["type"] == "number":
        validation = question.get("validation", {})
        placeholder = question.get("placeholder", "")
        prompt = question["label"]
        if placeholder:
            prompt += f" ({placeholder})"
        answer = questionary.text(
            prompt,
            validate=lambda val, v=validation: _validate_number(val, v),
        ).ask()
        if answer is None:
            return None
        return _parse_number_input(answer)

    if question["type"] == "select":
        choices = [opt["label"] for opt in question.get("options", [])]
        if question.get("allow_custom"):
            choices.append("Other (enter a number)")

        selected = questionary.select(question["label"], choices=choices).ask()
        if selected is None:
            return None

        if selected == "Other (enter a number)":
            validation = question.get("custom_validation", {})
            custom = questionary.text(
                f"Enter value ({validation.get('min', 0)}-{validation.get('max', 100)}):",
                validate=lambda val, v=validation: _validate_number(val, v),
            ).ask()
            if custom is None:
                return None
            return _parse_number_input(custom)

        for opt in question.get("options", []):
            if opt["label"] == selected:
                return opt["value"]

    return None


def _show_existing_response(db, session_id: str, survey_id: str) -> bool:
    """Check for existing response, display it, return True if it exists."""
    resp = db.execute(
        "SELECT * FROM survey_responses WHERE session_id = ? AND survey_id = ?",
        (session_id, survey_id),
    ).fetchone()

    if not resp:
        return False

    from open_uplift.cli.formatting import console, format_survey_results
    resp_dict = dict(resp)
    outputs = db.execute(
        "SELECT * FROM uplift_outputs WHERE survey_response_id = ?",
        (resp_dict["id"],),
    ).fetchall()
    outputs = [dict(o) for o in outputs]
    console.print(format_survey_results(resp_dict, outputs))
    return True


def run_survey(session_id: str, force: bool = False) -> None:
    """Run the interactive self-report survey based on the active survey config."""
    signal.signal(signal.SIGINT, _handle_sigint)

    init_db()
    with get_db() as db:
        survey = get_active_survey(db)

    print(f"\n--- Open Uplift: {survey['name']} (Ctrl+C to skip) ---")
    print(f"  Session: {session_id}\n")

    # Check for existing response
    with get_db() as db:
        has_existing = _show_existing_response(db, session_id, survey["id"])

    if has_existing:
        if force:
            print("Overriding existing response (--force).")
        else:
            override = questionary.confirm(
                "A response already exists. Override?", default=False
            ).ask()
            if not override:
                print("Keeping existing response.")
                return

        # Delete existing response
        with get_db() as db:
            delete_survey_response(db, session_id, survey["id"])
        print("Previous response deleted.\n")

    answers = {}
    for question in survey["questions"]:
        answer = _ask_question(question)
        if answer is None:
            return
        answers[question["id"]] = answer

    notes = questionary.text(
        "Any notes? (optional, press Enter to skip)",
    ).ask()
    if notes is None:
        notes = ""

    with get_db() as db:
        response_id, outputs = submit_survey_response(
            db, session_id, survey["id"], answers, notes
        )

    # Rich output for submission result
    from open_uplift.cli.formatting import console

    output_str = ", ".join(f"{o['output_id']}={round(o['uplift_factor'], 2)}" for o in outputs)
    console.print(f"\n[bold green]Report saved[/bold green] ({output_str}). Thanks!\n")
