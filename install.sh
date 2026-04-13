#!/usr/bin/env bash
# Airflow MCP Server — Interactive Setup
# Usage: bash install.sh
# Or:    curl -s https://raw.githubusercontent.com/<user>/airflow-mcp-server/main/install.sh | bash

set -euo pipefail

REPO_URL="https://github.com/abogdanov/airflow-mcp-server.git"
INSTALL_DIR="${AIRFLOW_MCP_DIR:-$HOME/airflow-mcp-server}"
CONFIG_DIR="$HOME/.config/airflow-mcp"
CONFIG_FILE="$CONFIG_DIR/config.yaml"

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

if [ -d "$INSTALL_DIR" ]; then
    echo "  Found existing installation at $INSTALL_DIR"
    cd "$INSTALL_DIR"
    git pull --quiet 2>/dev/null || echo "  (could not pull — using existing)"
else
    echo "  Cloning to $INSTALL_DIR..."
    git clone --quiet "$REPO_URL" "$INSTALL_DIR" 2>/dev/null || {
        echo "  Could not clone repo. Creating local installation instead."
        echo "  You'll need to copy the project files manually."
        mkdir -p "$INSTALL_DIR"
    }
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
echo "  eiga (Japan) · paa (APAC) · fpk (Korea) · fpt (Thailand)"
echo "  fps (Singapore) · fpm (Malaysia) · tlb (Talabat/MENA)"
echo "  hun (Hungerstation) · ped (PedidosYa) · gfg (GFG)"
echo "  dhp (DH Platform) · and more..."
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
        read -rp "    Session cookie (or press Enter to skip for now): " COOKIE
        echo "    auth:" >> "$CONFIG_FILE"
        echo "      type: dh_cookie" >> "$CONFIG_FILE"
        echo "      session_cookie: \"${COOKIE}\"" >> "$CONFIG_FILE"
    fi
    echo "" >> "$CONFIG_FILE"
done

echo ""
echo "  ✓ Config written to $CONFIG_FILE"
echo ""

# --- Claude Code settings ---
echo "[5/5] Claude Code integration..."
echo ""
echo "Add this to your Claude Code MCP settings:"
echo "(~/.claude/settings.json → mcpServers)"
echo ""
echo "  \"airflow\": {"
echo "    \"command\": \"$INSTALL_DIR/.venv/bin/python\","
echo "    \"args\": [\"-m\", \"airflow_mcp.server\"],"
echo "    \"cwd\": \"$INSTALL_DIR/src\","
echo "    \"env\": {"
echo "      \"AIRFLOW_MCP_CONFIG\": \"$CONFIG_FILE\""
echo "    }"
echo "  }"
echo ""

# --- Validate ---
echo "Validating config..."
AIRFLOW_MCP_CONFIG="$CONFIG_FILE" "$INSTALL_DIR/.venv/bin/python" -m airflow_mcp.cli validate 2>&1 || true

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║   Setup complete!                            ║"
echo "║                                              ║"
echo "║   Next steps:                                ║"
echo "║   1. Add the MCP settings above to Claude    ║"
echo "║   2. Restart Claude Code                     ║"
echo "║   3. Try: 'check my airflow standup'         ║"
echo "╚══════════════════════════════════════════════╝"
