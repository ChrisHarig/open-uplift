"""Validate plugin directory structure and file integrity."""

import json
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]


def test_plugin_json_valid():
    plugin_json = PLUGIN_DIR / ".claude-plugin" / "plugin.json"
    assert plugin_json.exists(), f"Missing {plugin_json}"
    data = json.loads(plugin_json.read_text())
    assert "name" in data, "plugin.json must have 'name'"
    assert "version" in data, "plugin.json must have 'version'"
    assert "description" in data, "plugin.json must have 'description'"


def test_skill_md_exists():
    skill_md = PLUGIN_DIR / "skills" / "uplift" / "SKILL.md"
    assert skill_md.exists(), f"Missing {skill_md}"
    content = skill_md.read_text()
    assert "open uplift" in content.lower(), "SKILL.md should mention Open Uplift"


def test_skill_md_has_frontmatter():
    skill_md = PLUGIN_DIR / "skills" / "uplift" / "SKILL.md"
    content = skill_md.read_text()
    assert content.startswith("---"), "SKILL.md should have YAML frontmatter"
    assert "description:" in content, "SKILL.md frontmatter should have description"


def test_skill_md_covers_survey():
    skill_md = PLUGIN_DIR / "skills" / "uplift" / "SKILL.md"
    content = skill_md.read_text()
    assert "survey" in content.lower(), "SKILL.md should cover survey functionality"


def test_skill_md_covers_cli_commands():
    skill_md = PLUGIN_DIR / "skills" / "uplift" / "SKILL.md"
    content = skill_md.read_text()
    assert "open-uplift serve" in content, "SKILL.md should document serve command"
    assert "open-uplift sync" in content, "SKILL.md should document sync command"
    assert "sessions" in content.lower(), "SKILL.md should document sessions"


def test_no_stale_hook_files():
    """Ensure old hook files have been cleaned up."""
    assert not (PLUGIN_DIR / "hooks").exists(), "hooks/ directory should be removed"
    assert not (PLUGIN_DIR / "scripts").exists(), "scripts/ directory should be removed"
