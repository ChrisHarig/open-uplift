import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("OPEN_UPLIFT_DATA_DIR", str(Path.home() / ".open-uplift")))
DB_PATH = DATA_DIR / "open-uplift.db"

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"

# Codex CLI data directory (respects CODEX_HOME env var)
CODEX_HOME = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))

DEFAULT_PORT = 7070

# Project root: __file__ = server/src/open_uplift/config.py → parents[3] = project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Dashboard build output (served as static files)
DASHBOARD_DIR = Path(os.environ.get("OPEN_UPLIFT_DASHBOARD_DIR", str(PROJECT_ROOT / "dashboard" / "dist")))

# Plugin paths
PLUGIN_DIR = PROJECT_ROOT / "plugin"
HOOKS_FILE = PLUGIN_DIR / "hooks" / "hooks.json"

# Default model pricing (USD per million tokens)
DEFAULT_PRICING = {
    "claude-opus-4-6": {
        "input": 15.0,
        "output": 75.0,
        "cache_read": 1.50,
        "cache_create": 18.75,
    },
    "claude-opus-4-5-20251101": {
        "input": 15.0,
        "output": 75.0,
        "cache_read": 1.50,
        "cache_create": 18.75,
    },
    "claude-sonnet-4-5-20250929": {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.30,
        "cache_create": 3.75,
    },
    "claude-haiku-4-5-20251001": {
        "input": 0.80,
        "output": 4.0,
        "cache_read": 0.08,
        "cache_create": 1.0,
    },
    # OpenAI models (used by Codex CLI)
    "o3": {
        "input": 2.0,
        "output": 8.0,
        "cache_read": 1.0,
        "cache_create": None,
    },
    "o4-mini": {
        "input": 1.10,
        "output": 4.40,
        "cache_read": 0.275,
        "cache_create": None,
    },
    "gpt-4.1": {
        "input": 2.0,
        "output": 8.0,
        "cache_read": 0.50,
        "cache_create": None,
    },
    "gpt-4.1-mini": {
        "input": 0.40,
        "output": 1.60,
        "cache_read": 0.10,
        "cache_create": None,
    },
    "gpt-4.1-nano": {
        "input": 0.10,
        "output": 0.40,
        "cache_read": 0.025,
        "cache_create": None,
    },
    "codex-mini": {
        "input": 1.50,
        "output": 6.0,
        "cache_read": 0.375,
        "cache_create": None,
    },
}


DEFAULT_SHARING_CONFIG = {
    "level": 1,  # 1 = aggregates only, 2 = aggregates + per-session summaries
    "stats": {
        "tokens": True,
        "cost": True,
        "messages": True,
        "tool_calls": True,
        "uplift": True,
        "compacted_transcripts": False,
        "full_transcripts": False,
    },
}

REPOS_DIR = DATA_DIR / "repos"

CUSTOM_TRANSCRIPTS_DIR = DATA_DIR / "transcripts"


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
