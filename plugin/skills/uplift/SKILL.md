---
description: Use the Open Uplift CLI tool for measuring engineering productivity, running surveys, syncing sessions, and managing configuration
---

# Open Uplift

You have access to the Open Uplift CLI tool (`open-uplift`) for measuring engineering productivity uplift from AI coding assistants. The dashboard server runs at `http://127.0.0.1:7070`.

## What Open Uplift Does

Open Uplift measures how much faster a developer works with AI by comparing actual session time against LLM-estimated time without AI. It reads Claude Code session transcripts, runs them through compaction and judging steps, and produces an uplift factor (e.g., 3.2x means the developer was ~3.2x faster with AI).

## Common Commands

### Server & Sync
```bash
open-uplift serve              # Start the dashboard server (auto-syncs on start)
open-uplift sync               # Sync Claude Code session data into the local DB
open-uplift explain            # Show a guided overview of the tool
```

### Sessions
```bash
open-uplift sessions                          # Interactive session picker
open-uplift sessions list                     # List recent sessions
open-uplift sessions list --project <name>    # Filter by project
open-uplift sessions list --search <term>     # Search sessions
open-uplift sessions show <session_id>        # Show session detail
open-uplift sessions show <session_id> --all  # Show everything (transcript, judge, survey, telemetry)
open-uplift sessions judge --session-id <id>  # Run compaction + LLM judge on one session
open-uplift sessions judge --all              # Judge all unjudged sessions
open-uplift sessions compact --session-id <id> # Run transcript compaction only
open-uplift sessions survey --session-id <id>  # Run the interactive survey CLI
```

### Configuration
```bash
open-uplift config scripts show        # Show current LLM provider/prompt config
open-uplift config surveys show-active # Show the active survey definition
open-uplift config surveys list        # List all surveys
open-uplift config batch-sync show     # Show scheduled processing settings
```

## Filling Out a Survey

If the user wants to fill out a survey (self-report) for a session, follow these steps:

1. **Get the active survey** by calling:
   ```bash
   curl -s http://127.0.0.1:7070/api/surveys/active
   ```
   This returns the survey definition with questions. If the server isn't running, tell the user to start it with `open-uplift serve`.

2. **Pick a session.** If the user provided a session ID or you know which session to report on, use that. Otherwise, fetch recent sessions:
   ```bash
   curl -s "http://127.0.0.1:7070/api/sessions?limit=10"
   ```
   Show the user a short list of their recent sessions (date, project, message count) and ask which one. Sessions that already have a survey response should be noted.

3. **Ask the survey questions** one at a time, conversationally. For each question:
   - Show the label and description
   - Present any options clearly
   - Let the user pick or enter a custom value if allowed
   - Do NOT require the user to fill out anything — if they want to skip, that's fine

4. **Optionally ask for notes** — a free-text field for anything they want to add.

5. **Submit the response**:
   ```bash
   curl -s -X POST http://127.0.0.1:7070/api/survey-responses \
     -H "Content-Type: application/json" \
     -d '{"session_id": "<SESSION_ID>", "survey_id": "<SURVEY_ID>", "answers": {<ANSWERS>}, "notes": "<NOTES>"}'
   ```
   The `answers` object maps question IDs to their numeric values.

6. **Confirm** the submission by showing the computed uplift outputs from the response.

## General Patterns

- The dashboard at `http://127.0.0.1:7070` provides a UI for everything the CLI can do.
- Data lives in `~/.open-uplift/` (SQLite DB, config). Session transcripts are read from `~/.claude/projects/`.
- Judging requires an API key (Anthropic by default). Keys can be added via the dashboard Settings or `open-uplift config scripts`.
- Organizations let users group sessions by team/project and optionally share aggregate metrics via a hub server.

## Important
- Keep interactions conversational and lightweight.
- The survey is voluntary — if the user wants to bail, let them.
- If the server isn't running, suggest `open-uplift serve` to start it.
