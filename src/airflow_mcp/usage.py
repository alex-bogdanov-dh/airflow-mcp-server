"""Optional local-only usage tracking. No telemetry, no network calls.

Writes a simple JSON counter file to ~/.local/share/airflow-mcp/usage.json.
Disabled by default — set AIRFLOW_MCP_TRACK_USAGE=1 to enable.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

USAGE_DIR = Path.home() / ".local" / "share" / "airflow-mcp"
USAGE_FILE = USAGE_DIR / "usage.json"
ENABLED = os.environ.get("AIRFLOW_MCP_TRACK_USAGE", "0") == "1"


def _load() -> dict:
    if USAGE_FILE.exists():
        try:
            return json.loads(USAGE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save(data: dict) -> None:
    USAGE_DIR.mkdir(parents=True, exist_ok=True)
    USAGE_FILE.write_text(json.dumps(data, indent=2))


def track(tool_name: str) -> None:
    """Increment the call counter for a tool. No-op if tracking disabled."""
    if not ENABLED:
        return
    data = _load()
    tools = data.setdefault("tools", {})
    tools[tool_name] = tools.get(tool_name, 0) + 1
    data["last_used"] = datetime.now(timezone.utc).isoformat()
    data["total_calls"] = sum(tools.values())
    _save(data)


def get_stats() -> str:
    """Return usage statistics as a formatted string."""
    if not USAGE_FILE.exists():
        return "No usage data. Set AIRFLOW_MCP_TRACK_USAGE=1 to enable tracking."

    data = _load()
    tools = data.get("tools", {})
    total = data.get("total_calls", 0)
    last = data.get("last_used", "never")

    lines = [f"Total calls: {total}", f"Last used: {last}", "", "Per tool:"]
    for name, count in sorted(tools.items(), key=lambda x: -x[1]):
        lines.append(f"  {name}: {count}")

    return "\n".join(lines)
