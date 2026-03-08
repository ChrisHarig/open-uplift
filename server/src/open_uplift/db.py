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
    total_input_tokens       INTEGER DEFAULT 0,
    total_output_tokens      INTEGER DEFAULT 0,
    total_cache_read_tokens  INTEGER DEFAULT 0,
    total_cache_create_tokens INTEGER DEFAULT 0,
    total_cost_usd   REAL DEFAULT 0.0,
    message_count    INTEGER DEFAULT 0,
    tool_call_count  INTEGER DEFAULT 0,
    model_primary    TEXT
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
    notes                 TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS model_pricing (
    model_name             TEXT PRIMARY KEY,
    input_cost_per_mtok    REAL NOT NULL,
    output_cost_per_mtok   REAL NOT NULL,
    cache_read_per_mtok    REAL,
    cache_create_per_mtok  REAL
);

CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp);
CREATE INDEX IF NOT EXISTS idx_sessions_started_at ON sessions(started_at);
CREATE INDEX IF NOT EXISTS idx_self_reports_timestamp ON self_reports(timestamp);
"""


def _migrate_db(db: sqlite3.Connection) -> None:
    """Run schema migrations. Safe to call repeatedly."""
    columns = [row[1] for row in db.execute("PRAGMA table_info(self_reports)").fetchall()]
    if "speedup_factor" not in columns:
        db.execute("ALTER TABLE self_reports ADD COLUMN speedup_factor REAL")
    db.execute("CREATE INDEX IF NOT EXISTS idx_self_reports_session_id ON self_reports(session_id)")

    # Survey system tables
    db.executescript("""
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
            survey_response_id  INTEGER NOT NULL REFERENCES survey_responses(id),
            output_id           TEXT NOT NULL,
            uplift_factor       REAL NOT NULL,
            metadata            TEXT DEFAULT '{}',
            timestamp           TEXT NOT NULL,
            UNIQUE(survey_response_id, output_id)
        );

        CREATE INDEX IF NOT EXISTS idx_survey_responses_session_id ON survey_responses(session_id);
        CREATE INDEX IF NOT EXISTS idx_survey_responses_timestamp ON survey_responses(timestamp);
        CREATE INDEX IF NOT EXISTS idx_uplift_outputs_response_id ON uplift_outputs(survey_response_id);
    """)

    # Phase 1: API keys table
    db.executescript("""
        CREATE TABLE IF NOT EXISTS api_keys (
            provider      TEXT NOT NULL,
            key_name      TEXT NOT NULL,
            encrypted_key TEXT NOT NULL,
            created_at    TEXT NOT NULL,
            last_used_at  TEXT,
            PRIMARY KEY (provider, key_name)
        );
    """)

    # Phase 2: scaffold column on sessions + scaffolds table
    session_columns = [row[1] for row in db.execute("PRAGMA table_info(sessions)").fetchall()]
    if "scaffold" not in session_columns:
        db.execute("ALTER TABLE sessions ADD COLUMN scaffold TEXT")
        db.execute("UPDATE sessions SET scaffold = tool_source WHERE scaffold IS NULL")

    db.executescript("""
        CREATE TABLE IF NOT EXISTS scaffolds (
            scaffold_id   TEXT PRIMARY KEY,
            display_name  TEXT NOT NULL,
            description   TEXT DEFAULT '',
            created_at    TEXT NOT NULL,
            api_token     TEXT NOT NULL
        );
    """)

    # Job queue table
    db.executescript("""
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
    """)

    # Phase 3: script_results + prompts tables
    db.executescript("""
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
            UNIQUE(session_id, script_id)
        );

        CREATE TABLE IF NOT EXISTS prompts (
            prompt_id     TEXT PRIMARY KEY,
            category      TEXT NOT NULL,
            name          TEXT NOT NULL,
            description   TEXT DEFAULT '',
            system_prompt TEXT NOT NULL,
            created_at    TEXT NOT NULL,
            is_default    INTEGER DEFAULT 0
        );
    """)

    # Track session message_count at script execution time for staleness detection
    sr_columns = {row[1] for row in db.execute("PRAGMA table_info(script_results)").fetchall()}
    if "session_message_count" not in sr_columns:
        db.execute("ALTER TABLE script_results ADD COLUMN session_message_count INTEGER")

    # Add session_id to uplift_outputs, make survey_response_id nullable
    uo_columns = {row[1] for row in db.execute("PRAGMA table_info(uplift_outputs)").fetchall()}
    if "session_id" not in uo_columns:
        db.executescript("""
            CREATE TABLE uplift_outputs_new (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id          TEXT,
                survey_response_id  INTEGER REFERENCES survey_responses(id),
                output_id           TEXT NOT NULL,
                uplift_factor       REAL NOT NULL,
                metadata            TEXT DEFAULT '{}',
                timestamp           TEXT NOT NULL,
                UNIQUE(session_id, output_id)
            );

            INSERT INTO uplift_outputs_new
                (id, session_id, survey_response_id, output_id, uplift_factor, metadata, timestamp)
            SELECT
                uo.id,
                sr.session_id,
                uo.survey_response_id,
                uo.output_id,
                uo.uplift_factor,
                uo.metadata,
                uo.timestamp
            FROM uplift_outputs uo
            LEFT JOIN survey_responses sr ON uo.survey_response_id = sr.id;

            DROP TABLE uplift_outputs;
            ALTER TABLE uplift_outputs_new RENAME TO uplift_outputs;

            CREATE INDEX IF NOT EXISTS idx_uplift_outputs_session_id ON uplift_outputs(session_id);
            CREATE INDEX IF NOT EXISTS idx_uplift_outputs_response_id ON uplift_outputs(survey_response_id);
        """)

    # Judge output schema: add output_schema column to prompts
    prompt_columns = {row[1] for row in db.execute("PRAGMA table_info(prompts)").fetchall()}
    if "output_schema" not in prompt_columns:
        db.execute("ALTER TABLE prompts ADD COLUMN output_schema TEXT")

    # Prompt versioning: archived_at, parent_prompt_id, version
    if "archived_at" not in prompt_columns:
        db.execute("ALTER TABLE prompts ADD COLUMN archived_at TEXT")
        db.execute("ALTER TABLE prompts ADD COLUMN parent_prompt_id TEXT")
        db.execute("ALTER TABLE prompts ADD COLUMN version INTEGER DEFAULT 1")

    # Judge outputs table (EAV-style storage for schema-defined fields)
    db.executescript("""
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

        CREATE INDEX IF NOT EXISTS idx_judge_outputs_session_id ON judge_outputs(session_id);
        CREATE INDEX IF NOT EXISTS idx_judge_outputs_field_name ON judge_outputs(field_name);
    """)

    # Organizations tables
    db.executescript("""
        CREATE TABLE IF NOT EXISTS organizations (
            org_id        TEXT PRIMARY KEY,
            name          TEXT NOT NULL UNIQUE,
            description   TEXT DEFAULT '',
            is_verified   INTEGER DEFAULT 0,
            created_at    TEXT NOT NULL
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

        CREATE INDEX IF NOT EXISTS idx_org_folders_org_id ON org_folders(org_id);
        CREATE INDEX IF NOT EXISTS idx_org_folders_folder_path ON org_folders(folder_path);
    """)

    # Org buildout: sharing_config column + hub tables
    org_columns = {row[1] for row in db.execute("PRAGMA table_info(organizations)").fetchall()}
    if "sharing_config" not in org_columns:
        db.execute("ALTER TABLE organizations ADD COLUMN sharing_config TEXT")

    db.executescript("""
        CREATE TABLE IF NOT EXISTS org_memberships (
            org_id            TEXT PRIMARY KEY,
            org_name          TEXT,
            member_name       TEXT NOT NULL,
            role              TEXT DEFAULT 'member',
            git_repo_url      TEXT NOT NULL,
            git_auth_token    TEXT,
            local_path        TEXT,
            sharing_config    TEXT,
            last_push_at      TEXT,
            last_pull_at      TEXT,
            config_changed    INTEGER DEFAULT 0,
            joined_at         TEXT NOT NULL
        );
    """)

    # is_local column on sessions (1 = local, 0 = remote/pulled)
    session_columns_latest = {row[1] for row in db.execute("PRAGMA table_info(sessions)").fetchall()}
    if "is_local" not in session_columns_latest:
        db.execute("ALTER TABLE sessions ADD COLUMN is_local INTEGER DEFAULT 1")

    # Continuation tracking columns on sessions
    if "continued_from" not in session_columns_latest:
        db.execute("ALTER TABLE sessions ADD COLUMN continued_from TEXT")
        db.execute("ALTER TABLE sessions ADD COLUMN continuation_type TEXT")

    # Migrate org_memberships from old (org_id, sync_url) PK to new org_id PK schema
    om_columns = {row[1] for row in db.execute("PRAGMA table_info(org_memberships)").fetchall()}
    if "sync_url" in om_columns:
        # Migrate org_memberships to v2 schema with hub_url column
        db.executescript("""
            CREATE TABLE IF NOT EXISTS org_memberships_v2 (
                org_id            TEXT PRIMARY KEY,
                org_name          TEXT,
                member_name       TEXT NOT NULL DEFAULT '',
                role              TEXT DEFAULT 'member',
                git_repo_url      TEXT NOT NULL DEFAULT '',
                git_auth_token    TEXT,
                local_path        TEXT,
                sharing_config    TEXT,
                last_push_at      TEXT,
                last_pull_at      TEXT,
                config_changed    INTEGER DEFAULT 0,
                joined_at         TEXT NOT NULL DEFAULT ''
            );
        """)
        # Copy git-based memberships (those with git_repo_url set)
        db.execute("""
            INSERT OR IGNORE INTO org_memberships_v2
                (org_id, org_name, member_name, role, git_repo_url, git_auth_token,
                 sharing_config, last_push_at, last_pull_at, config_changed, joined_at)
            SELECT
                org_id, org_name,
                COALESCE(member_name_in_repo, member_name, ''),
                COALESCE(role, 'member'),
                COALESCE(git_repo_url, sync_url, ''),
                git_auth_token,
                sharing_config, last_push_at, last_pull_at,
                COALESCE(config_changed, 0),
                COALESCE(last_push_at, '')
            FROM org_memberships
            WHERE git_repo_url IS NOT NULL AND git_repo_url != ''
        """)
        db.executescript("""
            DROP TABLE org_memberships;
            ALTER TABLE org_memberships_v2 RENAME TO org_memberships;
        """)

    # Drop old hub-only tables (safe for upgrades)
    db.executescript("""
        DROP TABLE IF EXISTS org_aggregate_snapshots;
        DROP TABLE IF EXISTS org_full_transcripts;
        DROP TABLE IF EXISTS org_compacted_transcripts;
        DROP TABLE IF EXISTS org_session_summaries;
    """)

    # Migrate org_memberships: drop git columns, add hub columns
    om_columns_v3 = {row[1] for row in db.execute("PRAGMA table_info(org_memberships)").fetchall()}
    if "git_repo_url" in om_columns_v3:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS org_memberships_v3 (
                org_id            TEXT PRIMARY KEY,
                org_name          TEXT,
                member_name       TEXT NOT NULL DEFAULT '',
                role              TEXT DEFAULT 'member',
                hub_url           TEXT,
                api_key           TEXT,
                sharing_config    TEXT,
                last_push_at      TEXT,
                last_pull_at      TEXT,
                joined_at         TEXT NOT NULL DEFAULT ''
            );
        """)
        db.execute("""
            INSERT OR IGNORE INTO org_memberships_v3
                (org_id, org_name, member_name, role, sharing_config,
                 last_push_at, last_pull_at, joined_at)
            SELECT
                org_id, org_name, member_name, role, sharing_config,
                last_push_at, last_pull_at, COALESCE(joined_at, '')
            FROM org_memberships
        """)
        db.executescript("""
            DROP TABLE org_memberships;
            ALTER TABLE org_memberships_v3 RENAME TO org_memberships;
        """)

    # pull_config column on org_memberships (controls what member pulls)
    om_cols_latest = {row[1] for row in db.execute("PRAGMA table_info(org_memberships)").fetchall()}
    if "pull_config" not in om_cols_latest:
        db.execute("ALTER TABLE org_memberships ADD COLUMN pull_config TEXT")

    # Hub tables for server-side org data
    db.executescript("""
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
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id        TEXT NOT NULL,
            member_name   TEXT NOT NULL,
            aggregate_data TEXT NOT NULL,
            pushed_at     TEXT NOT NULL,
            UNIQUE(org_id, member_name)
        );

        CREATE INDEX IF NOT EXISTS idx_hub_members_org_id ON hub_members(org_id);
        CREATE INDEX IF NOT EXISTS idx_hub_members_api_key ON hub_members(api_key);
        CREATE INDEX IF NOT EXISTS idx_hub_invites_org_id ON hub_invites(org_id);
        CREATE INDEX IF NOT EXISTS idx_hub_sessions_org_id ON hub_sessions(org_id);
        CREATE INDEX IF NOT EXISTS idx_hub_aggregates_org_id ON hub_aggregates(org_id);
    """)

    # Add org_mode column to organizations
    org_columns_latest = {row[1] for row in db.execute("PRAGMA table_info(organizations)").fetchall()}
    if "org_mode" not in org_columns_latest:
        db.execute("ALTER TABLE organizations ADD COLUMN org_mode TEXT")
        # Backfill: infer mode from hub_members + org_folders presence
        orgs = db.execute("SELECT org_id FROM organizations").fetchall()
        for org_row in orgs:
            oid = org_row["org_id"]
            has_hub = db.execute("SELECT 1 FROM hub_members WHERE org_id = ?", (oid,)).fetchone() is not None
            has_folders = db.execute("SELECT 1 FROM org_folders WHERE org_id = ?", (oid,)).fetchone() is not None
            if has_hub and has_folders:
                mode = "local_hub"
            elif has_hub:
                mode = "hub"
            else:
                mode = "local"
            db.execute("UPDATE organizations SET org_mode = ? WHERE org_id = ?", (mode, oid))

    # Normalize org_mode: legacy values (local, local_hub, personal) all become hub
    db.execute("UPDATE organizations SET org_mode = 'personal' WHERE org_mode = 'local'")
    db.execute("UPDATE organizations SET org_mode = 'hub' WHERE org_mode = 'local_hub'")
    db.execute("UPDATE organizations SET org_mode = 'hub' WHERE org_mode = 'personal'")

    # Auto-create hub admin + invite for migrated orgs missing them
    import secrets as _secrets
    orgs_without_admin = db.execute("""
        SELECT o.org_id FROM organizations o
        WHERE o.org_mode = 'hub'
          AND NOT EXISTS (SELECT 1 FROM hub_members hm WHERE hm.org_id = o.org_id AND hm.role = 'admin')
    """).fetchall()
    for org_row in orgs_without_admin:
        oid = org_row["org_id"]
        _now = datetime.now(timezone.utc).isoformat()
        db.execute(
            "INSERT OR IGNORE INTO hub_members (org_id, member_name, api_key, role, joined_at) VALUES (?, 'admin', ?, 'admin', ?)",
            (oid, _secrets.token_urlsafe(32), _now),
        )
        db.execute(
            "INSERT OR IGNORE INTO hub_invites (invite_code, org_id, created_by, created_at) VALUES (?, ?, 'admin', ?)",
            (_secrets.token_urlsafe(16), oid, _now),
        )

    # Add updated_at, source_member, source_org_id to sessions
    session_columns_v2 = {row[1] for row in db.execute("PRAGMA table_info(sessions)").fetchall()}
    if "updated_at" not in session_columns_v2:
        db.execute("ALTER TABLE sessions ADD COLUMN updated_at TEXT")
        db.execute("UPDATE sessions SET updated_at = started_at WHERE updated_at IS NULL")
    if "source_member" not in session_columns_v2:
        db.execute("ALTER TABLE sessions ADD COLUMN source_member TEXT")
    if "source_org_id" not in session_columns_v2:
        db.execute("ALTER TABLE sessions ADD COLUMN source_org_id TEXT")

    from open_uplift.surveys import seed_default_config, backfill_self_reports
    seed_default_config(db)
    backfill_self_reports(db)

    # Seed default prompts
    _seed_default_prompts(db)

    # Migrate flat llm_config → nested script_config
    _migrate_llm_to_script_config(db)



DEFAULT_JUDGE_OUTPUT_SCHEMA = [
    {"name": "success", "type": "boolean", "required": True, "description": "Whether the session produced useful output"},
    {"name": "total_minutes_without_ai", "type": "numeric", "required": True, "description": "Estimated minutes without AI"},
    {"name": "tasks", "type": "array", "required": True, "description": "List of subtasks with descriptions and time estimates"},
    {"name": "confidence", "type": "string", "required": True, "description": "Confidence level: low/medium/high"},
    {"name": "reasoning", "type": "string", "required": True, "description": "Brief explanation of the estimate"},
]

# The old hardcoded JSON block that gets removed from the system prompt when output_schema takes over
_OLD_JUDGE_JSON_BLOCK = (
    'Respond with JSON only:\n'
    '{\n'
    '  "success": true/false,\n'
    '  "tasks": [{"description": "...", "succeeded": true/false, "estimated_minutes_without_ai": N}],\n'
    '  "total_minutes_without_ai": N,\n'
    '  "confidence": "low"/"medium"/"high",\n'
    '  "reasoning": "Brief explanation"\n'
    '}'
)

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
}


def _seed_default_prompts(db: sqlite3.Connection) -> None:
    """Insert default prompts if they don't already exist."""
    import json as _json
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    for prompt_id, pdef in DEFAULT_PROMPTS.items():
        schema_json = _json.dumps(pdef["output_schema"]) if pdef.get("output_schema") else None
        db.execute(
            """INSERT OR IGNORE INTO prompts
               (prompt_id, category, name, description, system_prompt, created_at, is_default, output_schema)
               VALUES (?, ?, ?, ?, ?, ?, 1, ?)""",
            (prompt_id, pdef["category"], pdef["name"], pdef["description"], pdef["system_prompt"], now, schema_json),
        )

    # Migrate existing judge-default: set output_schema if missing, and strip hardcoded JSON block from prompt
    _migrate_judge_default_prompt(db)

    # Add continuation-awareness to existing default prompts
    _migrate_continuation_awareness(db)

    # Backfill judge_outputs from existing script_results
    _backfill_judge_outputs(db)


def _migrate_judge_default_prompt(db: sqlite3.Connection) -> None:
    """Set output_schema on judge-default and remove hardcoded JSON format block from its system_prompt."""
    import json as _json

    row = db.execute(
        "SELECT system_prompt, output_schema FROM prompts WHERE prompt_id = 'judge-default'"
    ).fetchone()
    if not row:
        return

    updates = {}

    # Set output_schema if not yet set
    if not row["output_schema"]:
        updates["output_schema"] = _json.dumps(DEFAULT_JUDGE_OUTPUT_SCHEMA)

    # Remove hardcoded JSON block from system_prompt if it matches exactly
    current_prompt = row["system_prompt"]
    if _OLD_JUDGE_JSON_BLOCK in current_prompt:
        new_prompt = current_prompt.replace("\n\n" + _OLD_JUDGE_JSON_BLOCK, "").replace(_OLD_JUDGE_JSON_BLOCK, "")
        updates["system_prompt"] = new_prompt.rstrip()

    if updates:
        set_clauses = ", ".join(f"{k} = ?" for k in updates)
        db.execute(
            f"UPDATE prompts SET {set_clauses} WHERE prompt_id = 'judge-default'",
            list(updates.values()),
        )


_OLD_JUDGE_SYSTEM_PROMPT = (
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
    "4. Estimate total minutes for the successful output only"
)

_OLD_COMPACTION_SYSTEM_PROMPT = (
    "You are a transcript compactor. Given a coding session transcript, produce a concise structured summary.\n\n"
    "Output format:\n"
    "## ACTIONS\n"
    "Chronological narrative of what happened. Include timestamps, tool names used, key decisions, brief code change descriptions, errors and resolutions.\n\n"
    "## OUTCOME\n"
    "- Success/failure assessment\n"
    "- What was produced (files modified, features implemented, bugs fixed)\n"
    "- Unresolved issues\n\n"
    "Exclude: verbose tool output, file contents that were just read, repeated content, system messages."
)


def _migrate_continuation_awareness(db: sqlite3.Connection) -> None:
    """Update existing judge-default and compaction-default prompts with continuation-aware text."""
    for prompt_id, old_text, new_text in [
        ("judge-default", _OLD_JUDGE_SYSTEM_PROMPT, DEFAULT_PROMPTS["judge-default"]["system_prompt"]),
        ("compaction-default", _OLD_COMPACTION_SYSTEM_PROMPT, DEFAULT_PROMPTS["compaction-default"]["system_prompt"]),
    ]:
        row = db.execute(
            "SELECT system_prompt FROM prompts WHERE prompt_id = ? AND archived_at IS NULL",
            (prompt_id,),
        ).fetchone()
        if row and row["system_prompt"] == old_text:
            db.execute(
                "UPDATE prompts SET system_prompt = ? WHERE prompt_id = ?",
                (new_text, prompt_id),
            )


def _backfill_judge_outputs(db: sqlite3.Connection) -> None:
    """Backfill judge_outputs from existing completed script_results."""
    import json as _json
    from datetime import datetime, timezone

    # Check if we already backfilled
    existing = db.execute("SELECT COUNT(*) as c FROM judge_outputs").fetchone()
    if existing["c"] > 0:
        return

    rows = db.execute(
        """SELECT session_id, result, prompt_id, completed_at
           FROM script_results
           WHERE script_id = 'llm-time-estimate' AND status = 'completed' AND result IS NOT NULL"""
    ).fetchall()

    now = datetime.now(timezone.utc).isoformat()
    for row in rows:
        try:
            result = _json.loads(row["result"])
        except (TypeError, _json.JSONDecodeError):
            continue

        session_id = row["session_id"]
        prompt_id = row["prompt_id"]
        created_at = row["completed_at"] or now

        # Extract known fields
        field_map = {
            "success": ("boolean", result.get("success")),
            "total_minutes_without_ai": ("numeric", result.get("total_minutes_without_ai")),
            "tasks": ("array", result.get("tasks")),
            "confidence": ("string", result.get("confidence")),
            "reasoning": ("string", result.get("reasoning")),
        }

        for field_name, (value_type, value) in field_map.items():
            if value is None:
                continue
            if value_type == "boolean":
                value_text = "true" if value else "false"
                value_numeric = 1.0 if value else 0.0
            elif value_type == "numeric":
                value_text = str(value)
                try:
                    value_numeric = float(value)
                except (ValueError, TypeError):
                    value_numeric = None
            elif value_type == "array":
                value_text = _json.dumps(value)
                value_numeric = None
            else:  # string
                value_text = str(value)
                value_numeric = None

            db.execute(
                """INSERT OR IGNORE INTO judge_outputs
                   (session_id, field_name, value_text, value_numeric, value_type, prompt_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (session_id, field_name, value_text, value_numeric, value_type, prompt_id, created_at),
            )


def _migrate_llm_to_script_config(db: sqlite3.Connection) -> None:
    """Convert flat llm_config to nested script_config. Idempotent."""
    import json as _json

    existing = db.execute("SELECT value FROM config WHERE key = 'script_config'").fetchone()
    if existing:
        return  # already migrated

    row = db.execute("SELECT value FROM config WHERE key = 'llm_config'").fetchone()
    if not row:
        return  # nothing to migrate

    flat = _json.loads(row["value"])
    nested = {
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
    db.execute(
        "INSERT INTO config (key, value) VALUES (?, ?)",
        ("script_config", _json.dumps(nested)),
    )


def init_db() -> None:
    """Create tables and seed pricing data."""
    ensure_data_dir()
    with get_db() as db:
        db.executescript(SCHEMA_SQL)
        _migrate_db(db)
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
