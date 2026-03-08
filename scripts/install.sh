#!/usr/bin/env bash
# Open Uplift — Install script
# Usage: bash scripts/install.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SERVER_DIR="$PROJECT_DIR/server"
DASHBOARD_DIR="$PROJECT_DIR/dashboard"
PLUGIN_DIR="$PROJECT_DIR/plugin"

echo "=== Open Uplift Installer ==="
echo ""

# --- 1. Check prerequisites ---
echo "[1/6] Checking prerequisites..."

if ! command -v python3 &>/dev/null; then
    echo "ERROR: Python 3.10+ is required."
    exit 1
fi

if ! command -v node &>/dev/null; then
    echo "ERROR: Node.js 18+ is required."
    exit 1
fi

if ! command -v npm &>/dev/null; then
    echo "ERROR: npm is required."
    exit 1
fi

echo "  Python: $(python3 --version)"
echo "  Node:   $(node --version)"
echo "  npm:    $(npm --version)"
echo ""

# --- 2. Install Python server + CLI ---
echo "[2/6] Installing server + CLI..."
cd "$SERVER_DIR"
python3 -m pip install --quiet -e .
echo "  CLI installed: $(command -v open-uplift || echo 'in PATH after shell restart')"
echo ""

# --- 3. Build React dashboard ---
echo "[3/6] Building dashboard..."
cd "$DASHBOARD_DIR"
npm install --silent
npm run build
echo "  Dashboard built: $DASHBOARD_DIR/dist/"
echo ""

# --- 4. Sync existing session data ---
echo "[4/6] Syncing session data..."
open-uplift sync
echo ""

# --- 5. Detect scaffolds and install integrations ---
echo "[5/6] Detecting AI coding tools..."
echo ""

DETECTED=()
INSTALLED=()

# Detect Claude Code
CLAUDE_DIR="$HOME/.claude"
if [ -d "$CLAUDE_DIR" ]; then
    DETECTED+=("claude_code")
    echo "  [found] Claude Code  (~/.claude/)"
else
    echo "  [  -  ] Claude Code  (not found)"
fi

# Detect Codex CLI
CODEX_HOME_DIR="${CODEX_HOME:-$HOME/.codex}"
if [ -d "$CODEX_HOME_DIR" ] || command -v codex &>/dev/null; then
    DETECTED+=("codex")
    echo "  [found] Codex CLI    (~/.codex/ or codex in PATH)"
else
    echo "  [  -  ] Codex CLI    (not found)"
fi

# Detect Cursor
if [ -d "$HOME/Library/Application Support/Cursor" ] || \
   [ -d "$HOME/.config/Cursor" ] || \
   [ -d "$APPDATA/Cursor" 2>/dev/null ]; then
    DETECTED+=("cursor")
    echo "  [found] Cursor       (Application Support)"
else
    echo "  [  -  ] Cursor       (not found)"
fi

echo ""

if [ ${#DETECTED[@]} -eq 0 ]; then
    echo "  No supported AI coding tools detected."
    echo "  You can still use the dashboard and CLI manually."
    echo "  Re-run this script after installing Claude Code, Codex, or Cursor."
    echo ""
else
    echo "  Which tools should Open Uplift integrate with?"
    echo "  (This installs a survey skill so you can report uplift from within each tool.)"
    echo ""

    SELECTED=()

    for tool in "${DETECTED[@]}"; do
        case "$tool" in
            claude_code) label="Claude Code" ;;
            codex)       label="Codex CLI" ;;
            cursor)      label="Cursor" ;;
        esac

        read -rp "  Install for $label? [Y/n] " answer
        answer="${answer:-Y}"
        if [[ "$answer" =~ ^[Yy] ]]; then
            SELECTED+=("$tool")
        fi
    done

    echo ""

    # --- Install for Claude Code ---
    if [[ " ${SELECTED[*]} " == *" claude_code "* ]]; then
        echo "  Setting up Claude Code..."
        CLAUDE_PLUGINS_DIR="$HOME/.claude/plugins"
        mkdir -p "$CLAUDE_PLUGINS_DIR"
        LINK_PATH="$CLAUDE_PLUGINS_DIR/open-uplift"
        if [ -L "$LINK_PATH" ] || [ -e "$LINK_PATH" ]; then
            rm -f "$LINK_PATH"
        fi
        ln -s "$PLUGIN_DIR" "$LINK_PATH"
        echo "    Plugin linked: $LINK_PATH -> $PLUGIN_DIR"
        echo "    Survey: use /open-uplift:survey in Claude Code"
        INSTALLED+=("Claude Code")
    fi

    # --- Install for Codex CLI ---
    if [[ " ${SELECTED[*]} " == *" codex "* ]]; then
        echo "  Setting up Codex CLI..."
        echo "    Note: Codex integration is planned but not yet available."
        echo "    Sessions from Codex are ingested automatically on sync."
        INSTALLED+=("Codex CLI (sync only)")
    fi

    # --- Install for Cursor ---
    if [[ " ${SELECTED[*]} " == *" cursor "* ]]; then
        echo "  Setting up Cursor..."
        echo "    Note: Cursor integration is limited — session data (tokens, model)"
        echo "    is not available locally. We can track session existence and surveys."
        # Cursor doesn't have a skill/plugin directory we can drop into easily.
        # For now, just ensure we sync Cursor's workspace data.
        echo "    Cursor sessions will be detected automatically on sync."
        INSTALLED+=("Cursor (limited)")
    fi

    echo ""
fi

# --- 6. Summary ---
echo "[6/6] Done!"
echo ""
echo "=== Installation Complete ==="
echo ""

if [ ${#INSTALLED[@]} -gt 0 ]; then
    echo "Integrations installed:"
    for t in "${INSTALLED[@]}"; do
        echo "  - $t"
    done
    echo ""
fi

echo "Usage:"
echo "  open-uplift serve       Start the dashboard at http://localhost:7070"
echo "  open-uplift sync        Re-sync session data from all detected tools"
echo "  open-uplift survey      Run a self-report survey from the CLI"
echo ""
echo "Next steps:"
echo "  1. Run: open-uplift serve"
echo "  2. Open: http://localhost:7070"
echo ""
