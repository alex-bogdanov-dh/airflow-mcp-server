# Airflow MCP Server

**The problem:** Debugging an Airflow DAG means opening the browser, navigating to the right instance, clicking through the DAG → Runs → Task → Logs pages, waiting for each to load, then copy-pasting the error. When you manage 10+ DDUs with separate Airflow instances, this takes 5-15 minutes per incident. During an on-call alert at 3am, that's 5-15 minutes too many.

**The fix:** This MCP server connects Claude Code directly to your Airflow instances. One tool call replaces 5 browser pages. `diagnose_dag_run("etl_orders", ddu="eiga")` gives you the failed run, the broken tasks, and the error logs — all in your terminal, in seconds.

## 30 Seconds to First Result

```bash
bash install.sh    # interactive setup: picks DDUs, writes config, done
```

Or manually:
```bash
git clone <this-repo>
cd airflow-mcp-server
uv venv && source .venv/bin/activate && uv pip install -e .
cp config.example.yaml ~/.config/airflow-mcp/config.yaml
# Edit config.yaml with your DDUs and auth
```

Add to Claude Code (`~/.claude/settings.json`):
```json
{
  "mcpServers": {
    "airflow": {
      "command": "/path/to/airflow-mcp-server/.venv/bin/python",
      "args": ["-m", "airflow_mcp.server"],
      "cwd": "/path/to/airflow-mcp-server/src",
      "env": {
        "AIRFLOW_MCP_CONFIG": "~/.config/airflow-mcp/config.yaml"
      }
    }
  }
}
```

Then ask Claude: *"Check my Airflow standup for eiga"*

## Before vs After

| Task | Before (Browser) | After (CLI) |
|------|-----------------|-------------|
| Check what's broken | Open Airflow → DAGs → filter failed → click each | `morning_standup(ddu="eiga")` |
| Read task logs | DAG → Runs → Run → Task → Logs → wait | `get_task_logs("etl", "run_1", "load")` |
| Full incident diagnosis | 5+ pages, 5-15 min | `diagnose_dag_run("etl")` — one call, 3 seconds |
| Morning standup message | Manually compile from UI | `slack_standup(ddu="eiga")` — paste into Slack |
| Re-run a DAG | Navigate → Trigger → fill form | `trigger_dag("etl")` |

## Tools

### Core Tools (direct API wrappers)
| Tool | What it does |
|------|-------------|
| `get_task_logs` | Fetch logs for a specific task instance |
| `get_dag_runs` | List recent DAG runs, filter by state |
| `get_failing_dags` | Find DAGs with failed latest runs |
| `trigger_dag` | Trigger a DAG run with optional config |
| `pause_dag` / `unpause_dag` | Pause/resume DAG scheduling |
| `get_connections` | List Airflow connections |

### Smart Composite Tools (multi-step in one call)
| Tool | What it does |
|------|-------------|
| `diagnose_dag_run` | Find failed run → task states → failed task logs |
| `morning_standup` | Failing + running + health stats |
| `slack_standup` | Same as standup, Slack mrkdwn formatted — paste ready |
| `alert_context` | Full incident context from just a dag_id |
| `get_dag_overview` | DAG metadata + schedule + recent run history |
| `get_task_instances` | All task states for a specific run |
| `get_team_dags` | Filter DAGs by team prefix/tag |
| `usage_stats` | Local usage tracking (opt-in) |

### Prompts (guided workflows)
| Prompt | Guides through... |
|--------|-------------------|
| `troubleshoot_failing_dag` | Full diagnosis → fix → re-run |
| `daily_health_check` | Morning standup routine |

## Multi-Instance (DDU)

Every tool accepts an optional `ddu` parameter. Configured instances:

```yaml
instances:
  eiga:
    base_url: "https://airflow-eiga.datahub.deliveryhero.net"
    auth:
      type: dh_cookie
      session_cookie: "..."
```

DH Airflow follows the pattern `airflow-{ddu}.datahub.deliveryhero.net`.

## Configuration

| Method | Path |
|--------|------|
| Env var | `AIRFLOW_MCP_CONFIG=/path/to/config.yaml` |
| Project dir | `./config.yaml` |
| User config | `~/.config/airflow-mcp/config.yaml` |

Auth types: `basic` (local), `dh_cookie` (SSO browser cookie), `dh_service_account` (planned).

## Local Development

```bash
# Start local Airflow
docker compose up -d
# Wait 30s, then:
AIRFLOW_MCP_CONFIG=config.docker.yaml airflow-mcp validate

# Run tests (45 tests, no Airflow needed)
uv pip install -e ".[dev]"
pytest
```

## Reliability

Transient errors (429, 502, 503) are retried with exponential backoff (3 attempts). Concurrent DAG checks are capped at 10 parallel requests to avoid overwhelming Airflow.

## Usage Tracking

Optional, local-only. Set `AIRFLOW_MCP_TRACK_USAGE=1` to enable. Call `usage_stats()` to see your numbers. No telemetry, no network calls.

---

Built by Alex Bogdanov | MIT License
