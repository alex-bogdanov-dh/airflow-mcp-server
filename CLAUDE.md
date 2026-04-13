# Airflow MCP Server — AI Agent Guide

This file tells Claude Code (and other AI agents) how to use this MCP server effectively.

## What This Server Does

Connects to Apache Airflow 3.x instances via REST API v2. Lets you check DAG status, read task logs, trigger runs, and diagnose failures — all without opening the Airflow UI.

## Quick Reference — Which Tool To Use

| You want to... | Use this tool |
|----------------|--------------|
| See what's broken right now | `morning_standup` |
| Get a Slack-ready standup message | `slack_standup` |
| Respond to a PagerDuty/OpsGenie alert | `alert_context` (just needs dag_id) |
| Investigate a specific failing DAG | `diagnose_dag_run` (does everything in one call) |
| Read logs for a specific task | `get_task_logs` |
| Check recent runs for a DAG | `get_dag_runs` |
| Get DAG metadata + schedule + recent runs | `get_dag_overview` |
| See which tasks failed in a run | `get_task_instances` |
| Find DAGs by team | `get_team_dags` |
| Re-run a DAG | `trigger_dag` |
| Stop a DAG from running | `pause_dag` |
| Resume a paused DAG | `unpause_dag` |
| Check connection configuration | `get_connections` |
| Check usage stats | `usage_stats` |

## Multi-Instance (DDU)

This server supports multiple Airflow instances. Each instance has a DDU code (e.g., `eiga`, `paa`, `local`). Every tool accepts an optional `ddu` parameter — omit it to use the default instance.

To see available instances: read the `airflow://instances` resource.

## Common Workflows

### "This DAG is failing, fix it"

**One call:** `diagnose_dag_run(dag_id="the_dag")` — automatically finds the latest failed run, shows all task states, and fetches logs for failed tasks.

### "I got paged about a DAG"

**One call:** `alert_context(dag_id="the_dag", ddu="eiga")` — returns DAG overview + full diagnosis. Everything you need for incident response.

### "Morning standup — what's broken?"

**One call:** `morning_standup()` — returns failing DAGs, currently running DAGs, and overall health stats.

**For Slack:** `slack_standup(ddu="eiga")` — same data, formatted with Slack mrkdwn. Copy and paste directly into your team channel.

### "Show me what my team owns"

`get_team_dags(team="identity", ddu="eiga")` — filters by DAG name prefix, owner, or tags.

### "Re-run a DAG after fixing"

```
trigger_dag(dag_id="the_dag")
```

If you need to pass config: `trigger_dag(dag_id="the_dag", conf='{"date": "2026-04-12"}')`

### "Stop alert storms from a broken DAG"

```
pause_dag(dag_id="the_dag")
# ... investigate and fix ...
unpause_dag(dag_id="the_dag")
```

## Delivery Hero Context

At DH, Airflow instances are per-DDU (Data Domain Unit):
- Each DDU has its own Airflow: `airflow-{ddu}.datahub.deliveryhero.net`
- Common DDUs: `eiga`, `paa`, `tlb`, `hun`, `fpk`, `gfg`, `dhp`, and more
- Auth uses session cookies (paste from browser) or GCP service accounts
- The platform team (Valentina, Niha) manages Airflow infrastructure
- DAGs often follow naming: `{team}_{domain}_{action}` — use `get_team_dags` to filter

When debugging DH DAGs:
1. Always specify the `ddu` parameter to hit the right instance
2. Connection errors often mean a Data Hub connection was misconfigured — check `get_connections`
3. If a DAG is owned by another team, check the owner field in `get_dag_overview`

## Prompts

Two pre-built guided workflows are available:
- `troubleshoot_failing_dag` — step-by-step diagnosis
- `daily_health_check` — morning routine

## Error Handling

All tools return human-readable error messages (never raw HTTP errors). If you see "Error in <tool>:", the message includes the HTTP status and reason. Transient errors (429, 502, 503) are automatically retried.
