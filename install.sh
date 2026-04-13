#!/usr/bin/env bash
# Airflow MCP Server — Interactive Setup
# Usage: bash install.sh
# Or:    curl -s https://raw.githubusercontent.com/alex-bogdanov-dh/airflow-mcp-server/main/install.sh | bash

set -euo pipefail

REPO_URL="https://github.com/alex-bogdanov-dh/airflow-mcp-server.git"
INSTALL_DIR="${AIRFLOW_MCP_DIR:-$HOME/airflow-mcp-server}"
CONFIG_DIR="$HOME/.config/airflow-mcp"
CONFIG_FILE="$CONFIG_DIR/config.yaml"
CLAUDE_JSON="$HOME/.claude.json"

echo "╔══════════════════════════════════════════════╗"
echo "║   Airflow MCP Server — Interactive Setup     ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# --- Check prerequisites ---
echo "[1/5] Checking prerequisites..."

if ! command -v python3 &>/dev/null; then
    echo "  ✗ Python 3 not found. Install Python 3.10+ first."
    exit 1
fi
echo "  ✓ Python $(python3 --version 2>&1 | cut -d' ' -f2)"

if command -v uv &>/dev/null; then
    echo "  ✓ uv $(uv --version 2>&1 | head -1)"
    PKG_MGR="uv"
else
    echo "  ⚠ uv not found (recommended). Using pip instead."
    echo "    Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
    PKG_MGR="pip"
fi

if command -v claude &>/dev/null; then
    echo "  ✓ Claude Code found"
else
    echo "  ⚠ Claude Code not found. Install it to use the MCP server."
fi
echo ""

# --- Clone or update ---
echo "[2/5] Setting up project..."

if [ -d "$INSTALL_DIR" ] && [ -f "$INSTALL_DIR/pyproject.toml" ]; then
    # Valid existing installation — update it
    echo "  Found existing installation at $INSTALL_DIR"
    cd "$INSTALL_DIR"
    git pull --quiet 2>/dev/null || echo "  (could not pull — using existing)"
elif [ -d "$INSTALL_DIR" ]; then
    # Directory exists but is not a valid project — remove and re-clone
    echo "  Found incomplete installation at $INSTALL_DIR — removing and re-cloning..."
    rm -rf "$INSTALL_DIR"
    echo "  Cloning to $INSTALL_DIR..."
    git clone --quiet "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
else
    echo "  Cloning to $INSTALL_DIR..."
    git clone --quiet "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# --- Install ---
echo "[3/5] Installing..."

if [ "$PKG_MGR" = "uv" ]; then
    uv venv --quiet .venv 2>/dev/null || true
    # shellcheck disable=SC1091
    source .venv/bin/activate
    uv pip install --quiet -e . 2>&1 | tail -1
else
    python3 -m venv .venv 2>/dev/null || true
    # shellcheck disable=SC1091
    source .venv/bin/activate
    pip install --quiet -e . 2>&1 | tail -1
fi
echo "  ✓ Installed"
echo ""

# --- Configure ---
echo "[4/5] Configuring Airflow instances..."
echo ""

mkdir -p "$CONFIG_DIR"

# DH DDU registry (known instances)
echo "Known Delivery Hero DDUs:"
echo "  eiga · paa · fpk · fpt · fps · fpm · tlb · hun · ped · gfg · dhp · and more..."
echo ""

read -rp "Enter DDU codes to configure (space-separated, e.g. 'eiga paa'): " DDU_INPUT
IFS=' ' read -ra DDUS <<< "${DDU_INPUT:-local}"

echo ""
echo "default_ddu: ${DDUS[0]}" > "$CONFIG_FILE"
echo "" >> "$CONFIG_FILE"
echo "instances:" >> "$CONFIG_FILE"

for DDU in "${DDUS[@]}"; do
    echo "  Configuring '$DDU'..."

    if [ "$DDU" = "local" ]; then
        BASE_URL="http://localhost:8080"
        AUTH_TYPE="basic"
    else
        BASE_URL="https://airflow-${DDU}.datahub.deliveryhero.net"
        AUTH_TYPE="dh_cookie"
    fi

    read -rp "    Base URL [$BASE_URL]: " CUSTOM_URL
    BASE_URL="${CUSTOM_URL:-$BASE_URL}"

    echo "  ${DDU}:" >> "$CONFIG_FILE"
    echo "    base_url: \"${BASE_URL}\"" >> "$CONFIG_FILE"

    if [ "$AUTH_TYPE" = "basic" ]; then
        read -rp "    Username [airflow]: " USERNAME
        USERNAME="${USERNAME:-airflow}"
        read -rsp "    Password [airflow]: " PASSWORD
        PASSWORD="${PASSWORD:-airflow}"
        echo ""
        echo "    auth:" >> "$CONFIG_FILE"
        echo "      type: basic" >> "$CONFIG_FILE"
        echo "      username: ${USERNAME}" >> "$CONFIG_FILE"
        echo "      password: ${PASSWORD}" >> "$CONFIG_FILE"
    else
        echo "    Auth: DH cookie (paste from browser after logging into Airflow)"
        echo "    Tip: run this in DevTools Console → copy(document.cookie)"
        echo "    Session cookie (or press Enter to skip for now):"
        read -r COOKIE
        echo "    auth:" >> "$CONFIG_FILE"
        echo "      type: dh_cookie" >> "$CONFIG_FILE"
        echo "      session_cookie: \"${COOKIE}\"" >> "$CONFIG_FILE"
    fi
    echo "" >> "$CONFIG_FILE"
done

echo ""
echo "  ✓ Config written to $CONFIG_FILE"
echo ""

# --- Claude Code integration (auto-write to ~/.claude.json) ---
echo "[5/5] Wiring into Claude Code..."

PYTHON_BIN="$INSTALL_DIR/.venv/bin/python"

python3 - << PYEOF
import json, os, sys

claude_json = os.path.expanduser("$CLAUDE_JSON")
install_dir = "$INSTALL_DIR"
config_file = "$CONFIG_FILE"

entry = {
    "type": "stdio",
    "command": f"{install_dir}/.venv/bin/python",
    "args": ["-m", "airflow_mcp.server"],
    "env": {
        "AIRFLOW_MCP_CONFIG": config_file
    }
}

if os.path.exists(claude_json):
    with open(claude_json) as f:
        d = json.load(f)
else:
    d = {}

if "mcpServers" not in d:
    d["mcpServers"] = {}

d["mcpServers"]["airflow"] = entry

with open(claude_json, "w") as f:
    json.dump(d, f, indent=4)

print(f"  ✓ MCP server registered in {claude_json}")
PYEOF

# --- Validate ---
echo ""
echo "Validating connectivity..."
AIRFLOW_MCP_CONFIG="$CONFIG_FILE" "$INSTALL_DIR/.venv/bin/python" -m airflow_mcp.cli validate 2>&1 || true

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   Setup complete!                            ║"
echo "║                                              ║"
echo "║   Next steps:                                ║"
echo "║   1. Restart Claude Code                     ║"
echo "║   2. Try: 'check my airflow standup'         ║"
echo "╚══════════════════════════════════════════════╝"
