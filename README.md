# Open Uplift

Measure how much AI coding tools speed up development per-session. Open Uplift tracks your sessions with AI assistants (Claude Code, Codex, etc.), uses an LLM judge to estimate how long tasks would take without AI, and computes uplift via time_with_ai/time_without_ai across projects and organizations.

## Features

- **Session tracking** — Automatically ingests telemetry from Claude Code sessions
- **LLM judge** — Compacts transcripts and estimates counterfactual time-without-AI
- **Uplift analytics** — Per-session, per-project, and per-organization uplift factors
- **Dashboard** — Web UI with charts, session browser, transcript viewer, and judge results
- **CLI** — Command-line interface for all operations
- **Organizations** — Create hubs to share aggregate uplift metrics across a team
- **Hub sync** — Members push and pull sessions down from a hub
- **Configurable prompts** — Editable judge and compaction prompts with output schemas
- **Scheduled batch runs** — Automatic sync + judge on a configurable schedule
- **Export** — CSV and JSON export of sessions with judge outputs, survey responses, and transcripts

## Installation

### From source (recommended)

Requires Python 3.10+.

```bash
git clone https://github.com/chrisharig/open-uplift.git
cd open-uplift
pip install ./server
```

Or with [pipx](https://pipx.pypa.io/) for an isolated install:

```bash
pipx install ./server
```

### Development setup

```bash
git clone https://github.com/chrisharig/open-uplift.git
cd open-uplift

# Server
pip install -e "server[dev]"

# Dashboard
cd dashboard && npm install

# Run both (separate terminals)
open-uplift serve            # API server on :7070
cd dashboard && npm run dev  # Vite dev server with hot reload
```

### Docker

```bash
docker build -t open-uplift .
docker run -p 7070:7070 -v open-uplift-data:/data open-uplift
```

Or with Docker Compose (hub + member setup):

```bash
docker compose up
# Hub:    http://localhost:7071
# Member: http://localhost:7072
```

## Quick Start

```bash
# 1. Sync session data from Claude Code
open-uplift sync

# 2. Launch the dashboard
open-uplift serve
# Open http://localhost:7070

# 3. Add an API key in Settings (or via CLI)
open-uplift config keys add anthropic

# 4. Judge all sessions
open-uplift sessions judge --all
```

## CLI Reference

```
open-uplift
  serve                   Start the dashboard server
  sync                    Import session data from Claude Code
  explain                 Setup guide and command tree

  sessions                Browse and manage sessions
    list                  List recent sessions
    show <id>             View session detail and transcript
    judge --all           Run LLM judge on unjudged sessions
    judge --stale         Re-judge sessions with new messages
    survey                Record self-reported time estimates
    run                   Run compaction or judge on individual sessions
    export                Export sessions to CSV or JSON

  orgs                    Manage organizations
    list                  List all organizations
    create <name>         Create a hub (generates admin key + invite code)
    show <org_id>         Organization detail and stats
    join <url>            Join a hub via URL + invite code
    sync                  Push/pull org data
    add-folders           Assign project folders to an org
    remove-folders        Unassign folders
    delete                Delete an organization

  config                  View and update configuration
    scripts show          Judge and compaction model settings
    scripts list-prompts  List prompts and output schemas
    scripts edit-prompt   Edit a prompt in $EDITOR
    profile show          Developer profile
    profile set           Set profile for judge context
    keys add              Store an API key
    keys list             List stored keys
    run-modes             Scheduled batch settings
```

## Development

```bash
# Server tests
pytest server/tests/ -v

# Dashboard tests
cd dashboard && npm test

# Lint
ruff check server/src/
```

## Claude Code Plugin

Open Uplift includes a Claude Code plugin that lets you run surveys, judge sessions, and manage configuration directly through your AI assistant.

To install, copy the plugin into your project:

```bash
cp -r plugin/.claude-plugin /path/to/your/project/.claude-plugin
cp -r plugin/skills /path/to/your/project/.claude/skills
```

## Coming Soon

- Electron desktop app 
- Plugin marketplace listing
- Support for Codex, Cursor, and custom scaffolds
- Git metrics like PR's reviewed by AI
- Multi-org hub support
- Richer judge features

## License

[MIT](LICENSE)