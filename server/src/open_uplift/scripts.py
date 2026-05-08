"""Script execution engine: dispatches to evaluator registry.

This module is the backward-compatible entry point. All helpers
(_get_script_config, _get_prompt, _get_tool_config, _get_transcript_path,
_preprocess_transcript, _store_result) remain here and are imported by
evaluator implementations.
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
        },
    }


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


def _get_tool_config(db: sqlite3.Connection, prompt_id: str) -> dict | None:
    """Get the tool-use config for a prompt, if any.

    Returns a dict with keys tool_name, tool_description, input_schema — or None
    if the prompt is text-only (no tool-use).
    """
    row = db.execute(
        "SELECT tool_config FROM prompts WHERE prompt_id = ?", (prompt_id,)
    ).fetchone()
    if not row or not row["tool_config"]:
        return None
    return json.loads(row["tool_config"])


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


# Tools that produce code diffs the judge must see verbatim. Matches METR's
# "preserving code diffs" rule from the methodology section.
_DIFF_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit", "Update"}


def _render_assistant_blocks(entry: dict) -> str:
    """Render one assistant entry's blocks into a single text segment.

    Used as input to the per-turn summarizer — non-diff tool inputs and results
    are truncated to keep the summarizer focused on the narrative. Code diffs
    (Edit/Write/etc.) are kept verbatim so the summarizer's narrative still
    reflects what was actually changed.
    """
    ts = entry.get("timestamp", "")[:19]
    parts = [f"[{ts}] ASSISTANT TURN"]
    for block in entry.get("blocks", []):
        if block["type"] == "text":
            text = block["text"]
            if len(text) > 1500:
                text = text[:1500] + "..."
            parts.append(f"TEXT: {text}")
        elif block["type"] == "tool_use":
            tool = block.get("tool_name", "unknown")
            raw_input = block.get("input", {})
            inp = json.dumps(raw_input)
            if tool not in _DIFF_TOOLS and len(inp) > 400:
                inp = inp[:400] + "..."
            result = block.get("result", "")
            if result and tool not in _DIFF_TOOLS and len(result) > 400:
                result = result[:400] + "..."
            is_error = " [ERROR]" if block.get("is_error") else ""
            parts.append(f"TOOL {tool}({inp}){is_error}")
            if result:
                parts.append(f"  RESULT: {result}")
    return "\n".join(parts)


def _extract_code_diffs(entry: dict) -> list[str]:
    """Return verbatim renderings of any Edit/Write/MultiEdit calls in this turn.

    Each diff is a multi-line string ready to be embedded in the final compacted
    transcript. Returns an empty list if the turn has no code-diff tools.
    """
    diffs: list[str] = []
    for block in entry.get("blocks", []):
        if block.get("type") != "tool_use":
            continue
        tool = block.get("tool_name", "")
        if tool not in _DIFF_TOOLS:
            continue
        inp = block.get("input", {}) or {}
        path = inp.get("file_path") or inp.get("notebook_path") or "<unknown>"
        is_error = " [ERROR]" if block.get("is_error") else ""
        if tool == "Edit":
            old = inp.get("old_string", "")
            new = inp.get("new_string", "")
            replace_all = inp.get("replace_all")
            header = f"--- {tool} {path}{is_error}"
            if replace_all:
                header += " (replace_all)"
            diffs.append(f"{header}\n--- old\n{old}\n--- new\n{new}")
        elif tool == "Write":
            content = inp.get("content", "")
            diffs.append(f"--- {tool} {path}{is_error}\n--- content\n{content}")
        elif tool == "MultiEdit":
            edits = inp.get("edits", []) or []
            edit_blocks = []
            for i, e in enumerate(edits):
                edit_blocks.append(
                    f"  edit[{i}]:\n  --- old\n{e.get('old_string', '')}\n  --- new\n{e.get('new_string', '')}"
                )
            diffs.append(f"--- {tool} {path}{is_error}\n" + "\n".join(edit_blocks))
        elif tool == "NotebookEdit":
            content = inp.get("new_source", "") or inp.get("content", "")
            diffs.append(f"--- {tool} {path}{is_error}\n--- new_source\n{content}")
        else:
            diffs.append(f"--- {tool} {path}{is_error}\n{json.dumps(inp)}")
    return diffs


def _render_user_text(entry: dict) -> str:
    """Render a user entry verbatim — no truncation, no summarization."""
    ts = entry.get("timestamp", "")[:19]
    text_parts = [b["text"] for b in entry.get("blocks", []) if b["type"] == "text"]
    body = "\n".join(text_parts).strip()
    if not body:
        return ""
    return f"[{ts}] USER: {body}"


def _segment_transcript_by_turn(transcript_data: dict) -> list[dict]:
    """Segment a parsed transcript into per-turn chunks for compaction.

    Each chunk is {"user_text": str, "assistant_text": str | None,
    "code_diffs": list[str]}. user_text and code_diffs are kept verbatim in the
    final compacted output (METR: "preserving code diffs"). assistant_text is
    what gets summarized by the per-turn LLM call.
    """
    entries = transcript_data.get("transcript", [])
    chunks: list[dict] = []
    current_user_text: str | None = None
    current_assistant_parts: list[str] = []
    current_diffs: list[str] = []
    leading_assistant_parts: list[str] = []
    leading_diffs: list[str] = []

    def flush():
        nonlocal current_user_text, current_assistant_parts, current_diffs
        if current_user_text is None and not current_assistant_parts and not current_diffs:
            return
        chunks.append({
            "user_text": current_user_text or "",
            "assistant_text": "\n".join(current_assistant_parts) if current_assistant_parts else None,
            "code_diffs": list(current_diffs),
        })
        current_user_text = None
        current_assistant_parts = []
        current_diffs = []

    for entry in entries:
        if entry["role"] == "user":
            user_rendered = _render_user_text(entry)
            if not user_rendered:
                continue
            if (leading_assistant_parts or leading_diffs) and not chunks and current_user_text is None:
                current_assistant_parts.extend(leading_assistant_parts)
                current_diffs.extend(leading_diffs)
                leading_assistant_parts = []
                leading_diffs = []
            flush()
            current_user_text = user_rendered
        elif entry["role"] == "assistant":
            rendered = _render_assistant_blocks(entry)
            diffs = _extract_code_diffs(entry)
            if current_user_text is None and not chunks:
                leading_assistant_parts.append(rendered)
                leading_diffs.extend(diffs)
            else:
                current_assistant_parts.append(rendered)
                current_diffs.extend(diffs)
    flush()

    if not chunks and (leading_assistant_parts or leading_diffs):
        chunks.append({
            "user_text": "[SESSION START — no user message in transcript]",
            "assistant_text": "\n".join(leading_assistant_parts) if leading_assistant_parts else None,
            "code_diffs": leading_diffs,
        })

    return chunks


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
