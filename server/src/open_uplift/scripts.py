"""Script execution engine: dispatches to evaluator registry.

This module is the backward-compatible entry point. All helpers
(_get_script_config, _get_prompt, _get_transcript_path, _preprocess_transcript,
_store_result) remain here and are imported by evaluator implementations.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from open_uplift.keystore import get_api_key  # noqa: F401 — evaluators access via _scripts.get_api_key; tests monkeypatch here


def run_script(db: sqlite3.Connection, script_id: str, session_id: str) -> dict:
    """Run a script/evaluator for a session. Returns result dict.

    Delegates to the evaluator registry. The returned dict maintains
    backward compatibility with the previous direct-execution approach.
    """
    from open_uplift.evaluators.registry import get_registry

    registry = get_registry()

    if registry.has(script_id):
        result = registry.run(db, script_id, session_id)
        # Convert EvaluatorResult back to the dict format callers expect
        if result.error:
            return {"error": result.error}
        return result.metadata if result.metadata else {"value": result.value}

    raise ValueError(f"Unknown script: {script_id}")


# --- Legacy wrapper functions (delegate to evaluators) ---

def run_transcript_compact(db: sqlite3.Connection, session_id: str) -> dict:
    """Compact a session transcript using an LLM."""
    return run_script(db, "transcript-compact", session_id)


def run_llm_time_estimate(db: sqlite3.Connection, session_id: str) -> dict:
    """Run the LLM judge to estimate time-without-AI."""
    return run_script(db, "llm-time-estimate", session_id)


# --- Helpers (used by evaluator implementations) ---


def _get_script_config(db: sqlite3.Connection) -> dict:
    """Get script configuration (nested format) from config table."""
    row = db.execute("SELECT value FROM config WHERE key = 'script_config'").fetchone()
    if row:
        return json.loads(row["value"])
    # Fall back to legacy flat llm_config and convert
    legacy = db.execute("SELECT value FROM config WHERE key = 'llm_config'").fetchone()
    if legacy:
        flat = json.loads(legacy["value"])
        return {
            "compaction": {
                "provider": flat.get("compaction_provider", "anthropic"),
                "model": flat.get("compaction_model", "claude-haiku-4-5-20251001"),
                "prompt_id": flat.get("compaction_prompt_id", "compaction-default"),
            },
            "judge": {
                "provider": flat.get("judge_provider", "anthropic"),
                "model": flat.get("judge_model", "claude-sonnet-4-6"),
                "prompt_id": flat.get("judge_prompt_id", "judge-default"),
            },
        }
    return {
        "compaction": {
            "provider": "anthropic",
            "model": "claude-haiku-4-5-20251001",
            "prompt_id": "compaction-default",
        },
        "judge": {
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "prompt_id": "judge-default",
        },
    }


# Backward-compat alias
_get_llm_config = _get_script_config


def _get_prompt(db: sqlite3.Connection, prompt_id: str) -> str:
    """Get a prompt's system_prompt text."""
    row = db.execute(
        "SELECT system_prompt FROM prompts WHERE prompt_id = ?", (prompt_id,)
    ).fetchone()
    if not row:
        raise ValueError(f"Prompt '{prompt_id}' not found")
    return row["system_prompt"]


def _build_prompt_with_schema(db: sqlite3.Connection, prompt_id: str) -> str:
    """Build system prompt with output schema instructions appended.

    Reads system_prompt + output_schema from the prompts table. If an
    output_schema exists, appends a structured "Output Schema" section
    that tells the LLM exactly what JSON fields to produce.
    """
    row = db.execute(
        "SELECT system_prompt, output_schema FROM prompts WHERE prompt_id = ?", (prompt_id,)
    ).fetchone()
    if not row:
        raise ValueError(f"Prompt '{prompt_id}' not found")

    system_prompt = row["system_prompt"]
    schema_raw = row["output_schema"]

    if not schema_raw:
        return system_prompt

    schema = json.loads(schema_raw)
    if not schema:
        return system_prompt

    # Build the output format instructions
    lines = [
        "",
        "## Output Schema",
        "Respond with a JSON object containing exactly these fields:",
        "",
    ]
    for field in schema:
        name = field["name"]
        ftype = field["type"]
        required = "required" if field.get("required") else "optional"
        desc = field.get("description", "")
        lines.append(f"- **{name}** ({ftype}, {required}): {desc}")

    lines.append("")
    lines.append("Respond with valid JSON only. No markdown fences, no extra text.")

    return system_prompt + "\n" + "\n".join(lines)


def _get_output_schema(db: sqlite3.Connection, prompt_id: str) -> list[dict] | None:
    """Get the output schema for a prompt, if any."""
    row = db.execute(
        "SELECT output_schema FROM prompts WHERE prompt_id = ?", (prompt_id,)
    ).fetchone()
    if not row or not row["output_schema"]:
        return None
    return json.loads(row["output_schema"])


def _get_transcript_path(db: sqlite3.Connection, session_id: str) -> Path | None:
    """Find the JSONL file path for a session."""
    row = db.execute(
        "SELECT file_path FROM ingest_log WHERE file_path LIKE ?",
        (f"%/{session_id}.jsonl",),
    ).fetchone()
    if row:
        path = Path(row["file_path"])
        if path.is_file():
            return path
    # Also check custom transcript dir
    from open_uplift.config import CUSTOM_TRANSCRIPTS_DIR

    for scaffold_dir in CUSTOM_TRANSCRIPTS_DIR.iterdir() if CUSTOM_TRANSCRIPTS_DIR.exists() else []:
        candidate = scaffold_dir / f"{session_id}.jsonl"
        if candidate.is_file():
            return candidate
    return None


def _store_result(
    db: sqlite3.Connection,
    session_id: str,
    script_id: str,
    status: str,
    result: dict | None,
    error: str | None,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    prompt_id: str | None,
    started_at: str,
) -> None:
    """Store or update script result."""
    now = datetime.now(timezone.utc).isoformat()
    # Capture current message_count for staleness detection
    sess_row = db.execute(
        "SELECT message_count FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    msg_count = sess_row["message_count"] if sess_row else 0
    db.execute(
        """INSERT INTO script_results
           (session_id, script_id, status, result, error, input_tokens, output_tokens,
            cost_usd, started_at, completed_at, prompt_id, session_message_count)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(session_id, script_id) DO UPDATE SET
               status = excluded.status,
               result = excluded.result,
               error = excluded.error,
               input_tokens = excluded.input_tokens,
               output_tokens = excluded.output_tokens,
               cost_usd = excluded.cost_usd,
               started_at = excluded.started_at,
               completed_at = excluded.completed_at,
               prompt_id = excluded.prompt_id,
               session_message_count = excluded.session_message_count""",
        (
            session_id, script_id, status,
            json.dumps(result) if result else None,
            error, input_tokens, output_tokens, cost_usd,
            started_at, now, prompt_id, msg_count,
        ),
    )


def _preprocess_transcript(transcript_data: dict) -> str:
    """Convert parsed transcript to a condensed text for LLM input."""
    lines = []
    for entry in transcript_data.get("transcript", []):
        role = entry["role"].upper()
        ts = entry.get("timestamp", "")[:19]
        for block in entry.get("blocks", []):
            if block["type"] == "text":
                text = block["text"]
                if len(text) > 500:
                    text = text[:500] + "..."
                lines.append(f"[{ts}] {role}: {text}")
            elif block["type"] == "tool_use":
                tool = block.get("tool_name", "unknown")
                inp = json.dumps(block.get("input", {}))
                if len(inp) > 200:
                    inp = inp[:200] + "..."
                result = block.get("result", "")
                if result and len(result) > 200:
                    result = result[:200] + "..."
                is_error = " [ERROR]" if block.get("is_error") else ""
                lines.append(f"[{ts}] {role} -> {tool}({inp}){is_error}")
                if result:
                    lines.append(f"  Result: {result}")
    return "\n".join(lines)


def _build_continuation_context(db: sqlite3.Connection, session_id: str) -> str:
    """Build a context preamble for continuation sessions.

    Returns an empty string if the session is not a continuation.
    """
    row = db.execute(
        "SELECT continuation_type FROM sessions WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if not row or not row["continuation_type"]:
        return ""

    ct = row["continuation_type"]
    if ct == "plan":
        return (
            "[CONTINUATION — PLAN]\n"
            "This session continues from a prior session where a plan was created. "
            "The plan loaded at the start of this session was already created before this session began. "
            "You are judging only the time it would take to complete the tasks shown in this session. "
            "Do NOT include the time to create the plan — judge from the completion of the plan onward."
        )
    elif ct == "general":
        return (
            "[CONTINUATION — COMPACTION]\n"
            "This session continues from a prior session that was split due to context window limits. "
            "Work shown as loaded context at the start of this session was already completed. "
            "You are judging only the time it would take to complete the NEW tasks shown in this session. "
            "Do NOT include time for work carried over from the prior session."
        )
    else:
        return (
            "[CONTINUATION]\n"
            "This session continues from a prior session. "
            "You are judging only the time it would take to complete the tasks shown in this session. "
            "Do NOT include time for work completed in prior sessions."
        )


def get_script_results(db: sqlite3.Connection, session_id: str) -> list[dict]:
    """Get all script results for a session."""
    rows = db.execute(
        "SELECT * FROM script_results WHERE session_id = ? ORDER BY started_at",
        (session_id,),
    ).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        if d.get("result"):
            d["result"] = json.loads(d["result"])
        results.append(d)
    return results
