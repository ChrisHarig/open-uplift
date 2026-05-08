import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator

from open_uplift.config import DB_PATH, DEFAULT_PRICING, ensure_data_dir

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS ingest_log (
    file_path    TEXT PRIMARY KEY,
    byte_offset  INTEGER NOT NULL DEFAULT 0,
    last_synced  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id       TEXT PRIMARY KEY,
    tool_source      TEXT NOT NULL DEFAULT 'claude_code',
    project_path     TEXT,
    project_name     TEXT,
    git_branch       TEXT,
    started_at       TEXT NOT NULL,
    ended_at         TEXT,
    updated_at       TEXT,
    total_input_tokens        INTEGER DEFAULT 0,
    total_output_tokens       INTEGER DEFAULT 0,
    total_cache_read_tokens   INTEGER DEFAULT 0,
    total_cache_create_tokens INTEGER DEFAULT 0,
    total_cost_usd   REAL DEFAULT 0.0,
    message_count    INTEGER DEFAULT 0,
    tool_call_count  INTEGER DEFAULT 0,
    model_primary    TEXT,
    scaffold         TEXT,
    is_local         INTEGER DEFAULT 1,
    continued_from   TEXT,
    continuation_type TEXT,
    source_member    TEXT,
    source_org_id    TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id       TEXT NOT NULL REFERENCES sessions(session_id),
    request_id       TEXT,
    timestamp        TEXT NOT NULL,
    role             TEXT NOT NULL,
    model            TEXT,
    input_tokens     INTEGER DEFAULT 0,
    output_tokens    INTEGER DEFAULT 0,
    cache_read_tokens INTEGER DEFAULT 0,
    cache_create_tokens INTEGER DEFAULT 0,
    cost_usd         REAL DEFAULT 0.0,
    tool_names       TEXT
);

CREATE TABLE IF NOT EXISTS self_reports (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id            TEXT,
    tool_source           TEXT NOT NULL DEFAULT 'claude_code',
    timestamp             TEXT NOT NULL,
    task_type             TEXT NOT NULL,
    complexity            TEXT NOT NULL,
    duration_minutes      INTEGER NOT NULL,
    perceived_speedup_pct INTEGER NOT NULL,
    ai_quality_rating     INTEGER NOT NULL,
    notes                 TEXT DEFAULT '',
    speedup_factor        REAL
);

CREATE TABLE IF NOT EXISTS model_pricing (
    model_name             TEXT PRIMARY KEY,
    input_cost_per_mtok    REAL NOT NULL,
    output_cost_per_mtok   REAL NOT NULL,
    cache_read_per_mtok    REAL,
    cache_create_per_mtok  REAL
);

CREATE TABLE IF NOT EXISTS config (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS survey_responses (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT,
    survey_id     TEXT NOT NULL,
    tool_source   TEXT NOT NULL DEFAULT 'claude_code',
    timestamp     TEXT NOT NULL,
    answers       TEXT NOT NULL,
    notes         TEXT DEFAULT '',
    UNIQUE(session_id, survey_id)
);

CREATE TABLE IF NOT EXISTS uplift_outputs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          TEXT,
    survey_response_id  INTEGER REFERENCES survey_responses(id),
    output_id           TEXT NOT NULL,
    uplift_factor       REAL NOT NULL,
    metadata            TEXT DEFAULT '{}',
    timestamp           TEXT NOT NULL,
    UNIQUE(session_id, output_id)
);

CREATE TABLE IF NOT EXISTS api_keys (
    provider      TEXT NOT NULL,
    key_name      TEXT NOT NULL,
    encrypted_key TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    last_used_at  TEXT,
    PRIMARY KEY (provider, key_name)
);

CREATE TABLE IF NOT EXISTS scaffolds (
    scaffold_id   TEXT PRIMARY KEY,
    display_name  TEXT NOT NULL,
    description   TEXT DEFAULT '',
    created_at    TEXT NOT NULL,
    api_token     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id            TEXT PRIMARY KEY,
    job_type      TEXT NOT NULL,
    status        TEXT DEFAULT 'pending',
    payload       TEXT NOT NULL,
    progress      TEXT DEFAULT '{}',
    error         TEXT,
    created_at    TEXT NOT NULL,
    started_at    TEXT,
    completed_at  TEXT
);

CREATE TABLE IF NOT EXISTS script_results (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT NOT NULL,
    script_id     TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',
    result        TEXT,
    error         TEXT,
    input_tokens  INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cost_usd      REAL DEFAULT 0.0,
    started_at    TEXT,
    completed_at  TEXT,
    prompt_id     TEXT,
    session_message_count INTEGER,
    UNIQUE(session_id, script_id)
);

CREATE TABLE IF NOT EXISTS prompts (
    prompt_id        TEXT PRIMARY KEY,
    category         TEXT NOT NULL,
    name             TEXT NOT NULL,
    description      TEXT DEFAULT '',
    system_prompt    TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    is_default       INTEGER DEFAULT 0,
    output_schema    TEXT,
    archived_at      TEXT,
    parent_prompt_id TEXT,
    version          INTEGER DEFAULT 1,
    tool_config      TEXT
);

CREATE TABLE IF NOT EXISTS judge_outputs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL,
    field_name      TEXT NOT NULL,
    value_text      TEXT,
    value_numeric   REAL,
    value_type      TEXT NOT NULL,
    prompt_id       TEXT,
    created_at      TEXT NOT NULL,
    UNIQUE(session_id, field_name)
);

CREATE TABLE IF NOT EXISTS organizations (
    org_id        TEXT PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,
    description   TEXT DEFAULT '',
    is_verified   INTEGER DEFAULT 0,
    created_at    TEXT NOT NULL,
    sharing_config TEXT,
    org_mode      TEXT
);

CREATE TABLE IF NOT EXISTS org_folders (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id        TEXT NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
    folder_path   TEXT NOT NULL UNIQUE,
    added_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS org_prompt_dismissed (
    folder_path   TEXT PRIMARY KEY,
    dismissed_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS org_memberships (
    org_id            TEXT PRIMARY KEY,
    org_name          TEXT,
    member_name       TEXT NOT NULL DEFAULT '',
    role              TEXT DEFAULT 'member',
    hub_url           TEXT,
    api_key           TEXT,
    sharing_config    TEXT,
    pull_config       TEXT,
    last_push_at      TEXT,
    last_pull_at      TEXT,
    joined_at         TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS hub_members (
    member_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id        TEXT NOT NULL,
    member_name   TEXT NOT NULL,
    api_key       TEXT NOT NULL UNIQUE,
    role          TEXT DEFAULT 'member',
    joined_at     TEXT NOT NULL,
    last_push_at  TEXT
);

CREATE TABLE IF NOT EXISTS hub_invites (
    invite_code   TEXT PRIMARY KEY,
    org_id        TEXT NOT NULL,
    created_by    TEXT,
    created_at    TEXT NOT NULL,
    revoked_at    TEXT
);

CREATE TABLE IF NOT EXISTS hub_sessions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id        TEXT NOT NULL,
    member_name   TEXT NOT NULL,
    session_id    TEXT NOT NULL,
    session_data  TEXT NOT NULL,
    pushed_at     TEXT NOT NULL,
    UNIQUE(org_id, session_id)
);

CREATE TABLE IF NOT EXISTS hub_aggregates (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id         TEXT NOT NULL,
    member_name    TEXT NOT NULL,
    aggregate_data TEXT NOT NULL,
    pushed_at      TEXT NOT NULL,
    UNIQUE(org_id, member_name)
);

CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);
CREATE INDEX IF NOT EXISTS idx_sessions_started_at ON sessions(started_at);
CREATE INDEX IF NOT EXISTS idx_self_reports_timestamp ON self_reports(timestamp);
CREATE INDEX IF NOT EXISTS idx_self_reports_session_id ON self_reports(session_id);
CREATE INDEX IF NOT EXISTS idx_survey_responses_session_id ON survey_responses(session_id);
CREATE INDEX IF NOT EXISTS idx_survey_responses_timestamp ON survey_responses(timestamp);
CREATE INDEX IF NOT EXISTS idx_uplift_outputs_session_id ON uplift_outputs(session_id);
CREATE INDEX IF NOT EXISTS idx_uplift_outputs_response_id ON uplift_outputs(survey_response_id);
CREATE INDEX IF NOT EXISTS idx_judge_outputs_session_id ON judge_outputs(session_id);
CREATE INDEX IF NOT EXISTS idx_judge_outputs_field_name ON judge_outputs(field_name);
CREATE INDEX IF NOT EXISTS idx_org_folders_org_id ON org_folders(org_id);
CREATE INDEX IF NOT EXISTS idx_org_folders_folder_path ON org_folders(folder_path);
CREATE INDEX IF NOT EXISTS idx_hub_members_org_id ON hub_members(org_id);
CREATE INDEX IF NOT EXISTS idx_hub_members_api_key ON hub_members(api_key);
CREATE INDEX IF NOT EXISTS idx_hub_invites_org_id ON hub_invites(org_id);
CREATE INDEX IF NOT EXISTS idx_hub_sessions_org_id ON hub_sessions(org_id);
CREATE INDEX IF NOT EXISTS idx_hub_aggregates_org_id ON hub_aggregates(org_id);
"""





DEFAULT_JUDGE_OUTPUT_SCHEMA = [
    {"name": "success", "type": "boolean", "required": True, "description": "Whether the session produced useful output"},
    {"name": "total_minutes_without_ai", "type": "numeric", "required": True, "description": "Estimated minutes without AI"},
    {"name": "tasks", "type": "array", "required": True, "description": "List of subtasks with descriptions and time estimates"},
    {"name": "confidence", "type": "string", "required": True, "description": "Confidence level: low/medium/high"},
    {"name": "reasoning", "type": "string", "required": True, "description": "Brief explanation of the estimate"},
]

AMY_COMPACTION_TOOL_CONFIG = {
    "tool_name": "summarize_turn",
    "tool_description": "Provide a concise two-part summary of one assistant turn in the conversation.",
    "input_schema": {
        "type": "object",
        "properties": {
            "actions": {
                "type": "string",
                "description": (
                    "High-level description of what the agent did, NOT at the tool-call level. "
                    "Examples of GOOD actions: 'Explored the codebase by reading configuration and test files, then designed a solution involving three new functions, and drafted a plan for user review'; "
                    "'Investigated the bug by running tests and examining stack traces, identified the root cause as a race condition'; "
                    "'Implemented the requested feature by creating a new module, updating the entry point, and adding tests'. "
                    "BAD (too granular): 'Called Read tool on config.py, called Bash...'."
                ),
            },
            "outcome": {
                "type": "string",
                "description": (
                    "What the agent produced. Use one of these formats: "
                    "'Drafted a plan to [brief description]', "
                    "'Provided explanation that [brief description]', "
                    "'Wrote code to [brief description]', "
                    "'Asked clarifying question about [topic]', "
                    "'Encountered error: [brief description]', "
                    "'Completed research on [topic]'."
                ),
            },
        },
        "required": ["actions", "outcome"],
    },
}

AMY_JUDGE_TOOL_CONFIG = {
    "tool_name": "tag_difficulty",
    "tool_description": "Estimate the human time to reproduce the successful net output of this session without AI.",
    "input_schema": {
        "type": "object",
        "properties": {
            "success": {
                "type": "boolean",
                "description": "Whether the session produced any useful net output.",
            },
            "tasks": {
                "type": "array",
                "description": "List of identified tasks with success status and per-task time estimates.",
                "items": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                        "succeeded": {"type": "boolean"},
                        "estimated_minutes_without_ai": {"type": "number"},
                    },
                    "required": ["description", "succeeded", "estimated_minutes_without_ai"],
                },
            },
            "total_minutes_without_ai": {
                "type": "number",
                "description": "Total estimated minutes for an experienced engineer to produce the same successful net output without AI.",
            },
            "confidence": {
                "type": "string",
                "enum": ["low", "medium", "high"],
            },
            "reasoning": {
                "type": "string",
                "description": "Brief explanation of how the estimate was derived and what was excluded.",
            },
        },
        "required": ["success", "tasks", "total_minutes_without_ai", "confidence", "reasoning"],
    },
}


# The full prompt templates from METR's Appendix A, verbatim. The
# {assistant_turn_content} / {compressed_transcript} placeholders are filled at
# call time and the entire interpolated string is sent as the sole user message
# (with an empty system prompt) so the model sees the prompt exactly as it
# appears in the article.

AMY_COMPACTION_TEMPLATE = (
    "You are summarizing an AI coding assistant's turn in a conversation.\n"
    "\n"
    "## Assistant Turn Content\n"
    "{assistant_turn_content}\n"
    "\n"
    "## Instructions\n"
    "Provide a concise summary with exactly two parts:\n"
    "\n"
    "1. ACTIONS: Describe what the agent did at a high level, NOT at the tool-call level.\n"
    "   Good examples:\n"
    "   - \"Explored the codebase by reading configuration files and test files, then designed\n"
    "     a solution involving three new functions, and drafted a plan for user review\"\n"
    "   - \"Investigated the bug by running tests and examining stack traces, identified the\n"
    "     root cause as a race condition in the cache layer\"\n"
    "   - \"Implemented the requested feature by creating a new module with helper functions,\n"
    "     updating the main entry point, and adding comprehensive tests\"\n"
    "\n"
    "   Bad examples (too granular):\n"
    "   - \"Called Read tool on config.py, called Read tool on test_main.py, called Bash...\"\n"
    "   - \"Used Edit tool to modify line 42, then used Edit tool again to modify line 58...\"\n"
    "\n"
    "2. OUTCOME: What did the agent produce? Use one of these formats:\n"
    "   - \"Drafted a plan to [brief description]\"\n"
    "   - \"Provided explanation that [brief description]\"\n"
    "   - \"Wrote code to [brief description]\"\n"
    "   - \"Asked clarifying question about [topic]\"\n"
    "   - \"Encountered error: [brief description]\"\n"
    "   - \"Completed research on [topic]\"\n"
    "\n"
    "Note: Code diffs are tracked separately. Focus on the narrative of what happened.\n"
    "\n"
    "Use the summarize_turn tool to provide your summary."
)


AMY_JUDGE_TEMPLATE = (
    "You are estimating how long an experienced software engineer who has full context\n"
    "would take to produce the NET SUCCESSFUL output of this coding session.\n"
    "\n"
    "## Instructions\n"
    "1. Read through the compressed transcript below and identify the overall task(s)\n"
    "   that the user is trying to complete. Each task might happen over multiple back\n"
    "   and forths between the user and the assistant.\n"
    "2. Identify which user requests were successfully completed (user approved or\n"
    "   moved on). This might happen over multiple turns.\n"
    "3. Identify which requests failed (user rejected, asked to redo, or explicitly\n"
    "   disapproved). Failed requests might also happen over multiple turns.\n"
    "4. For SUCCESSFUL work only, estimate the human time to produce equivalent output\n"
    "5. Failed/rejected work = 0 minutes (the output wasn't accepted)\n"
    "6. All work that's related to coding agent setup should have 0 estimated minutes.\n"
    "   Such tasks include writing to CLAUDE.md files, finding a previous agent session,\n"
    "   setting up a subagent or skill, researching how to use coding agents, creating\n"
    "   infrastructure for using and tracking multi-agent orchestration systems, etc.\n"
    "   These tasks should all receive 0 estimated minutes, even if they succeeded. The\n"
    "   work is not part of the net output because if the human didn't use coding agents,\n"
    "   they would not need to spend time setting up the agents.\n"
    "7. Sometimes the user would ask clarifying questions about the output, which is not\n"
    "   a failure, unless eventually the user provides failure signals.\n"
    "8. Sometimes the user is not asking for code to be produced, but rather a plan or\n"
    "   an explanation. This is normal and should be considered as a valid task.\n"
    "9. When code diffs are produced by the agent, use the code diffs in addition to the\n"
    "   task description to determine the complexity of the task. When looking at the code\n"
    "   diffs, don't just consider the diff quantity, since each line of code has different\n"
    "   complexity. Look at the code diffs and assess whether the changes that's made is\n"
    "   complex vs. simple for an experience software engineer to make, and make time\n"
    "   estimates based on your best judgment.\n"
    "10. The compressed transcript would only show a summary of the agent's outputs unless\n"
    "    there's code written. Do not consider it a failure just because the summary was\n"
    "    shown for a task, and you cannot see the full output. Read the summary and use\n"
    "    your best judgment to decide whether the task was a success or failure.\n"
    "\n"
    "\n"
    "## Success Signals\n"
    "- User says \"looks good\", \"great\", \"thanks\", then moves to new topic → SUCCESS\n"
    "- User says \"now do X\" building on previous work → previous work SUCCEEDED\n"
    "- User moves to completely new topic without complaint → implicit SUCCESS\n"
    "\n"
    "## Failure Signals\n"
    "- User says \"that's wrong\", \"try again\", \"fix this\" → FAILURE\n"
    "- User explicitly rejects or asks to revert → FAILURE\n"
    "- User expresses confusion about incorrect output → FAILURE\n"
    "\n"
    "## Example task 1\n"
    "USER: [asks to build a feature]\n"
    "ASSISTANT: [makes a plan to build a feature]\n"
    "USER: [clarifies the plan and ask the assistant to edit the plan according to\n"
    "additional requirements]\n"
    "ASSISTANT: [modifies the plan]\n"
    "USER: [approves the plan and asks the assistant to implement it]\n"
    "ASSISTANT: [implements the feature, discovers a bug in its own implementation\n"
    "and fixes it]\n"
    "USER: [ask questions about the implementation]\n"
    "ASSISTANT: [answers the questions]\n"
    "USER: [moves on to a new task]\n"
    "In this task, the feature was successfully built and the user moved on.\n"
    "You should estimate the time it would take an experienced software engineer to\n"
    "plan and implement the same feature. Even though the agent had a self-discovered\n"
    "bug fix, this is agent overhead and should not be counted in the time estimate.\n"
    "Only estimate the time to produce the final output: the plan AND the implementation.\n"
    "\n"
    "## Example task 2\n"
    "USER: [asks to build a feature]\n"
    "ASSISTANT: [makes a plan to build a feature]\n"
    "USER: [decides they no longer want to build this feature, asks for a new feature]\n"
    "ASSISTANT: [makes a plan for the new feature]\n"
    "USER: [approves the plan and asks the assistant to implement it]\n"
    "In this task, you should estimate the total time it would take for an experienced\n"
    "engineer to design the new feature, and ignore the time it would take to design\n"
    "the original feature. Since we care about the NET work that got done; given the\n"
    "original feature was abandoned, the engineer would not need to spend time on it.\n"
    "\n"
    "## Example task 3\n"
    "USER: [help me find the previous agent session that does X]\n"
    "ASSISTANT: [finds the session]\n"
    "USER: [summarize what that session implemented, then implement what it left out of\n"
    "a particular issue description]\n"
    "ASSISTANT: [summarizes, finds what the other session left out, and implements the\n"
    "remaining issue]\n"
    "If an experienced software engineer were to work on the task alone, they would not\n"
    "need to spend time finding and summarizing previous agent sessions. You should only\n"
    "consider the time it takes the engineer to implement the remaining issue, as that\n"
    "is the NET work that got done in this session, ignoring the form factor of working\n"
    "with coding agents.\n"
    "\n"
    "## Example task 4\n"
    "USER: [ask the agent to do something]\n"
    "ASSISTANT: [tries to do the task, but fails]\n"
    "USER: exits the session\n"
    "We should assume that the request failed, and since the NET output was nothing,\n"
    "the estimated time should be 0 minutes.\n"
    "\n"
    "## Example task 5\n"
    "USER: [random chats with the agent, not asking the agent to do anything]\n"
    "ASSISTANT: [chats with the user]\n"
    "USER: [asks about a new claude code feature]\n"
    "ASSISTANT: [explains the feature]\n"
    "USER: exits the session\n"
    "Casual chats or agent setup related work produces no NET output, thus the estimated\n"
    "time should be 0 minutes.\n"
    "\n"
    "## Compressed Transcript\n"
    "{compressed_transcript}\n"
    "\n"
    "Use the tag_difficulty tool to provide your estimate."
)

# Backwards-compat aliases — the templates ARE the prompts now (no system/user split).
AMY_COMPACTION_SYSTEM_PROMPT = AMY_COMPACTION_TEMPLATE
AMY_JUDGE_SYSTEM_PROMPT = AMY_JUDGE_TEMPLATE


DEFAULT_PROMPTS = {
    "compaction-default": {
        "category": "compaction",
        "name": "Default Compaction",
        "description": "Standard transcript compaction prompt",
        "system_prompt": (
            "You are a transcript compactor. Given a coding session transcript, produce a concise structured summary.\n\n"
            "Output format:\n"
            "## ACTIONS\n"
            "Chronological narrative of what happened. Include timestamps, tool names used, key decisions, brief code change descriptions, errors and resolutions.\n\n"
            "## OUTCOME\n"
            "- Success/failure assessment\n"
            "- What was produced (files modified, features implemented, bugs fixed)\n"
            "- Unresolved issues\n\n"
            "If the transcript begins with a [CONTINUATION] block, note this in the OUTCOME section. A session that ends with a plan or context handoff to a future session is not a failure — summarize what was produced in this session only.\n\n"
            "Exclude: verbose tool output, file contents that were just read, repeated content, system messages."
        ),
    },
    "judge-default": {
        "category": "judge",
        "name": "Default Judge",
        "description": "METR-inspired time estimation prompt",
        "system_prompt": (
            "You are an expert engineering time estimator. Given a summary of a coding session where an AI assisted an engineer, "
            "estimate how long an experienced software engineer would take to accomplish the SAME successful output WITHOUT any AI assistance.\n\n"
            "Instructions:\n"
            "1. Identify each subtask in the session\n"
            "2. For each subtask, determine if it succeeded (useful output produced)\n"
            "3. Exclude from your time estimate:\n"
            "   - Failed tasks or dead ends\n"
            "   - Agent overhead (retries, self-correction, verbose planning)\n"
            "   - Abandoned work that produced no useful output\n"
            "   - Time spent explaining things to the AI\n"
            "   - Spurious corrections a human wouldn't need to make\n"
            "4. Estimate total minutes for the successful output only\n"
            "5. If this is a continuation session (indicated by a [CONTINUATION] block), a planning-only session that produced a clear plan IS successful output — estimate the time to create that plan. Judge only the work done in THIS session."
        ),
        "output_schema": DEFAULT_JUDGE_OUTPUT_SCHEMA,
    },
    "compaction-amy": {
        "category": "compaction",
        "name": "Amy-Deng-Per-Turn-Compaction",
        "description": "METR/Amy-Deng per-turn compaction prompt, verbatim from Appendix A. Tool-use (anthropic/openai only).",
        "system_prompt": AMY_COMPACTION_SYSTEM_PROMPT,
        "tool_config": AMY_COMPACTION_TOOL_CONFIG,
    },
    "judge-amy": {
        "category": "judge",
        "name": "Amy-Deng-Judge",
        "description": "METR/Amy-Deng time-without-AI estimator, verbatim from Appendix A. Tool-use (anthropic/openai only).",
        "system_prompt": AMY_JUDGE_SYSTEM_PROMPT,
        "output_schema": DEFAULT_JUDGE_OUTPUT_SCHEMA,
        "tool_config": AMY_JUDGE_TOOL_CONFIG,
    },
}


def _seed_default_prompts(db: sqlite3.Connection) -> None:
    """Insert default prompts if they don't already exist."""
    import json as _json

    now = datetime.now(timezone.utc).isoformat()
    # Amy prompts must stay verbatim with the METR appendix — overwrite even if a
    # prior version is in the DB. Other defaults are insert-or-ignore so user
    # customizations are preserved.
    AMY_IDS = {"compaction-amy", "judge-amy"}
    for prompt_id, pdef in DEFAULT_PROMPTS.items():
        schema_json = _json.dumps(pdef["output_schema"]) if pdef.get("output_schema") else None
        tool_json = _json.dumps(pdef["tool_config"]) if pdef.get("tool_config") else None
        if prompt_id in AMY_IDS:
            db.execute(
                """INSERT INTO prompts
                   (prompt_id, category, name, description, system_prompt, created_at, is_default, output_schema, tool_config)
                   VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
                   ON CONFLICT(prompt_id) DO UPDATE SET
                       category = excluded.category,
                       name = excluded.name,
                       description = excluded.description,
                       system_prompt = excluded.system_prompt,
                       output_schema = excluded.output_schema,
                       tool_config = excluded.tool_config""",
                (prompt_id, pdef["category"], pdef["name"], pdef["description"], pdef["system_prompt"], now, schema_json, tool_json),
            )
        else:
            db.execute(
                """INSERT OR IGNORE INTO prompts
                   (prompt_id, category, name, description, system_prompt, created_at, is_default, output_schema, tool_config)
                   VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)""",
                (prompt_id, pdef["category"], pdef["name"], pdef["description"], pdef["system_prompt"], now, schema_json, tool_json),
            )
            if tool_json is not None:
                db.execute(
                    "UPDATE prompts SET tool_config = ? WHERE prompt_id = ? AND (tool_config IS NULL OR tool_config = '')",
                    (tool_json, prompt_id),
                )



def init_db() -> None:
    """Create tables, seed config + default prompts + model pricing."""
    ensure_data_dir()
    with get_db() as db:
        db.executescript(SCHEMA_SQL)
        from open_uplift.surveys import seed_default_config
        seed_default_config(db)
        _seed_default_prompts(db)
        for model_name, prices in DEFAULT_PRICING.items():
            db.execute(
                """INSERT OR IGNORE INTO model_pricing
                   (model_name, input_cost_per_mtok, output_cost_per_mtok,
                    cache_read_per_mtok, cache_create_per_mtok)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    model_name,
                    prices["input"],
                    prices["output"],
                    prices["cache_read"],
                    prices["cache_create"],
                ),
            )


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Get a SQLite connection with WAL mode and row factory."""
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
