# Airflow MCP Server

MCP server for Apache Airflow 3.x with multi-instance support and pluggable auth.

Debug DAGs, check runs, fetch logs, trigger re-runs — all from Claude Code without touching the Airflow UI.

## Quick Start

```bash
# Clone and install
git clone <this-repo-url>
cd airflow-mcp-server
uv venv && source .venv/bin/activate
uv pip install -e .

# Configure
cp config.example.yaml config.yaml
# Edit config.yaml with your Airflow instance(s)

# Add to Claude Code (see below)
```

## Tools

### Core Tools

| Tool | What it does |
|------|-------------|
| `get_task_logs` | Fetch logs for a specific task instance |
| `get_dag_runs` | List recent DAG runs, filter by state |
| `get_failing_dags` | Find DAGs with failed latest runs |
| `trigger_dag` | Trigger a DAG run with optional conf |
| `pause_dag` / `unpause_dag` | Pause/resume DAG scheduling |
| `get_connections` | List Airflow connections |

### Smart Composite Tools

These do multiple API calls in one tool invocation — designed to reduce token cost for AI agents:

| Tool | What it does |
|------|-------------|
| `diagnose_dag_run` | Find failed run → get task states → fetch failed task logs |
| `get_dag_overview` | DAG metadata + schedule + recent run history |
| `morning_standup` | Failing DAGs + running DAGs + health stats |
| `get_task_instances` | All task states for a specific run |

### Prompts

| Prompt | Guides the agent through... |
|--------|---------------------------|
| `troubleshoot_failing_dag` | Full diagnosis workflow for a broken DAG |
| `daily_health_check` | Morning standup routine |

Every tool accepts an optional `ddu` parameter to target a specific Airflow instance.

## Configuration

### Config File

Copy `config.example.yaml` to `config.yaml` and edit:

```yaml
default_ddu: local

instances:
  local:
    base_url: "http://localhost:8080"
    auth:
      type: basic
      username: airflow
      password: airflow

  # Add more instances:
  # production:
  #   base_url: "https://airflow.example.com"
  #   auth:
  #     type: dh_cookie
  #     session_cookie: "session=..."
```

### Config Search Order

1. `AIRFLOW_MCP_CONFIG` environment variable (explicit path)
2. `./config.yaml` (current working directory)
3. `~/.config/airflow-mcp/config.yaml` (user config directory)

### Auth Types

| Type | Config keys | Use case |
|------|------------|----------|
| `basic` | `username`, `password` | Local Airflow, simple setups |
| `dh_cookie` | `session_cookie` | SSO-protected Airflow (paste cookie from browser) |
| `dh_service_account` | — | GCP service account (planned, not yet implemented) |

## Claude Code Integration

Add to your Claude Code MCP settings (`~/.claude/settings.json` or project-level):

```json
{
  "mcpServers": {
    "airflow": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/airflow-mcp-server", "airflow-mcp"],
      "env": {}
    }
  }
}
```

Alternative with plain Python:

```json
{
  "mcpServers": {
    "airflow": {
      "command": "/path/to/airflow-mcp-server/.venv/bin/python",
      "args": ["-m", "airflow_mcp.server"],
      "cwd": "/path/to/airflow-mcp-server/src",
      "env": {}
    }
  }
}
```

You can also set the config path via env var:

```json
{
  "mcpServers": {
    "airflow": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/airflow-mcp-server", "airflow-mcp"],
      "env": {
        "AIRFLOW_MCP_CONFIG": "/path/to/your/config.yaml"
      }
    }
  }
}
```

## Airflow API

Targets Airflow 3.x REST API v2 (`/api/v2/`) exclusively. No v1 support.

## Local Airflow (Docker)

Spin up a local Airflow for testing:

```bash
docker compose up -d
# Wait ~30s for init, then:
AIRFLOW_MCP_CONFIG=config.docker.yaml airflow-mcp validate
```

Web UI at http://localhost:8080 (admin: airflow/airflow). Shut down: `docker compose down -v`.

## Validate Config

Check that your config is valid and all instances are reachable:

```bash
airflow-mcp validate
```

This loads the config, tests connectivity to each instance, and reports Airflow version.

## Development

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# Run tests (45 tests, no Airflow required)
pytest

# Run server directly
python -m airflow_mcp.server
```

## Reliability

Transient errors (HTTP 429, 502, 503) are automatically retried with exponential backoff (3 attempts, max 5s between retries). Permanent errors (401, 404, etc.) fail immediately.

## License

MIT
