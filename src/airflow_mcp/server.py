"""Airflow MCP Server — multi-instance, pluggable auth, Airflow 3.x API v2."""

from __future__ import annotations

import asyncio
import json
from typing import Annotated, Literal

from fastmcp import FastMCP

from .client import AirflowClient
from .config import Config, get_version
from .usage import track

mcp = FastMCP("Airflow MCP Server")

_config: Config | None = None
_clients: dict[str, AirflowClient] = {}

MAX_CONCURRENT_REQUESTS = 10


def _get_config() -> Config:
    global _config
    if _config is None:
        _config = Config()
    return _config


def _client(ddu: str | None = None) -> AirflowClient:
    """Get or create a cached AirflowClient for the given DDU."""
    instance = _get_config().resolve(ddu)
    if instance.ddu not in _clients:
        _clients[instance.ddu] = AirflowClient(instance)
    return _clients[instance.ddu]


def _extract_list(data: dict | list, key: str) -> list:
    """Extract a list from Airflow's paginated response envelope."""
    if isinstance(data, list):
        return data
    return data.get(key, [])


def _format_error(tool_name: str, e: Exception) -> str:
    """Consistent error formatting for tool responses."""
    return f"Error in {tool_name}: {type(e).__name__}: {e}"


def _format_run(run: dict) -> str:
    """Format a DAG run as a single line."""
    return (
        f"  {run.get('dag_run_id', '?')} | "
        f"state={run.get('state', '?')} | "
        f"start={run.get('start_date', '?')} | "
        f"end={run.get('end_date', '-')}"
    )


async def _check_latest_run(
    client: AirflowClient, dag_id: str, sem: asyncio.Semaphore,
) -> tuple[str, str, dict | None]:
    """Check a DAG's latest run. Returns (dag_id, state, run_dict_or_None)."""
    async with sem:
        try:
            runs_data = await client.get(
                f"/dags/{dag_id}/dagRuns",
                params={"limit": 1, "order_by": "-start_date"},
            )
            runs = _extract_list(runs_data, "dag_runs")
            if runs:
                return dag_id, runs[0].get("state", "unknown"), runs[0]
            return dag_id, "no_runs", None
        except Exception as exc:
            return dag_id, f"error: {type(exc).__name__}: {exc}", None


DagState = Literal["success", "failed", "running", "queued"]


@mcp.resource("airflow://instances")
def list_instances() -> str:
    """List all configured Airflow instances (DDU codes and base URLs).

    Use this to discover which DDU codes are available before calling tools.
    """
    cfg = _get_config()
    lines = [f"Default DDU: {cfg.default_ddu}", "", "Configured instances:"]
    for ddu, url in cfg.instances_summary.items():
        marker = " (default)" if ddu == cfg.default_ddu else ""
        lines.append(f"  {ddu}: {url}{marker}")
    return "\n".join(lines)


@mcp.resource("airflow://version")
def server_version() -> str:
    """Server version and capabilities summary."""
    return json.dumps({
        "version": get_version(),
        "api": "Airflow 3.x REST API v2 (/api/v2/)",
        "auth_types": ["basic", "dh_cookie", "dh_service_account"],
        "prompts": ["troubleshoot_failing_dag", "daily_health_check"],
    }, indent=2)


@mcp.tool
async def get_task_logs(
    dag_id: Annotated[str, "The DAG ID, e.g. 'etl_orders_daily'"],
    run_id: Annotated[str, "The DAG run ID, e.g. 'scheduled__2026-04-13T00:00:00+00:00'"],
    task_id: Annotated[str, "The task ID within the DAG, e.g. 'extract_orders'"],
    try_number: Annotated[int, "Attempt number, 1-based. Use 1 for first try, 2 for first retry."] = 1,
    ddu: Annotated[str | None, "DDU instance code (e.g. 'eiga', 'paa', 'local'). Uses default if omitted."] = None,
) -> str:
    """Fetch logs for a specific task instance.

    This is the highest-value tool — it's what saves you from opening the Airflow UI.
    You need the dag_id, run_id, and task_id. Get these from get_dag_runs or diagnose_dag_run.

    Example: get_task_logs(dag_id="etl_orders", run_id="scheduled__2026-04-13T00:00:00+00:00", task_id="load_to_bq")
    """
    track("get_task_logs")
    client = _client(ddu)
    try:
        return await client.fetch_task_log(dag_id, run_id, task_id, try_number)
    except Exception as e:
        return _format_error("get_task_logs", e)


@mcp.tool
async def get_dag_runs(
    dag_id: Annotated[str, "The DAG ID, e.g. 'etl_orders_daily'"],
    limit: Annotated[int, "Maximum number of runs to return (1-100)"] = 10,
    state: Annotated[DagState | None, "Filter by state: 'success', 'failed', 'running', or 'queued'. Omit for all states."] = None,
    ddu: Annotated[str | None, "DDU instance code. Uses default if omitted."] = None,
) -> str:
    """List recent DAG runs sorted by start date (newest first).

    Use this to check if a DAG is running, find recent failures, or get run IDs
    for use with get_task_logs or diagnose_dag_run.

    Example: get_dag_runs(dag_id="etl_orders", state="failed", limit=5)
    """
    client = _client(ddu)
    params: dict = {"limit": limit, "order_by": "-start_date"}
    if state:
        params["state"] = state
    try:
        data = await client.get(f"/dags/{dag_id}/dagRuns", params=params)
    except Exception as e:
        return _format_error("get_dag_runs", e)

    runs = _extract_list(data, "dag_runs")
    if not runs:
        return f"No runs found for '{dag_id}'."
    header = f"DAG runs for '{dag_id}'" + (f" (state={state})" if state else "")
    return header + "\n" + "\n".join(_format_run(r) for r in runs)


@mcp.tool
async def get_failing_dags(
    ddu: Annotated[str | None, "DDU instance code. Uses default if omitted."] = None,
    limit: Annotated[int, "Max DAGs to check (1-200)"] = 50,
) -> str:
    """Find all DAGs whose most recent run failed.

    Checks every active DAG's latest run concurrently (capped at 10 parallel requests).
    Use this for a quick health check. For a richer view, use morning_standup instead.

    Example: get_failing_dags(ddu="eiga")
    """
    client = _client(ddu)

    try:
        dags_data = await client.get("/dags", params={"limit": limit, "only_active": "true"})
    except Exception as e:
        return _format_error("get_failing_dags", e)

    dags = _extract_list(dags_data, "dags")
    sem = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    results = await asyncio.gather(
        *(_check_latest_run(client, d["dag_id"], sem) for d in dags if d.get("dag_id"))
    )

    failing = []
    for dag_id, state, run in results:
        if state == "failed" and run:
            failing.append(f"  {dag_id} | run={run.get('dag_run_id', '?')} | failed at {run.get('end_date', '?')}")
        elif state.startswith("error:"):
            failing.append(f"  {dag_id} | {state}")

    if not failing:
        return "No failing DAGs found. All clear."
    return f"Failing DAGs ({len(failing)}):\n" + "\n".join(failing)


@mcp.tool
async def trigger_dag(
    dag_id: Annotated[str, "The DAG ID to trigger, e.g. 'etl_orders_daily'"],
    conf: Annotated[str | None, "JSON config string for the run, e.g. '{\"date\": \"2026-04-12\"}'. Omit for no config."] = None,
    ddu: Annotated[str | None, "DDU instance code. Uses default if omitted."] = None,
) -> str:
    """Trigger a new DAG run, optionally with JSON configuration.

    Use this to manually re-run a DAG or trigger an ad-hoc execution.
    The conf parameter must be a valid JSON string if provided.

    Example: trigger_dag(dag_id="etl_orders", conf='{"backfill_date": "2026-04-12"}')
    """
    client = _client(ddu)
    body: dict = {}
    if conf:
        try:
            body["conf"] = json.loads(conf)
        except json.JSONDecodeError:
            return f"Invalid JSON in conf: {conf}"

    try:
        data = await client.post(f"/dags/{dag_id}/dagRuns", json=body)
    except Exception as e:
        return _format_error("trigger_dag", e)

    run_id = data.get("dag_run_id", "?")
    state = data.get("state", "?")
    return f"Triggered DAG '{dag_id}' — run_id={run_id}, state={state}"


@mcp.tool
async def pause_dag(
    dag_id: Annotated[str, "The DAG ID to pause"],
    ddu: Annotated[str | None, "DDU instance code. Uses default if omitted."] = None,
) -> str:
    """Pause a DAG to stop it from being scheduled.

    Useful to stop alert storms from a broken DAG while you investigate.
    The DAG will not run again until unpaused.

    Example: pause_dag(dag_id="etl_broken_pipeline", ddu="eiga")
    """
    client = _client(ddu)
    try:
        await client.patch(f"/dags/{dag_id}", json={"is_paused": True})
    except Exception as e:
        return _format_error("pause_dag", e)
    return f"DAG '{dag_id}' is now paused."


@mcp.tool
async def unpause_dag(
    dag_id: Annotated[str, "The DAG ID to unpause"],
    ddu: Annotated[str | None, "DDU instance code. Uses default if omitted."] = None,
) -> str:
    """Unpause a previously paused DAG to resume scheduling.

    Example: unpause_dag(dag_id="etl_broken_pipeline", ddu="eiga")
    """
    client = _client(ddu)
    try:
        await client.patch(f"/dags/{dag_id}", json={"is_paused": False})
    except Exception as e:
        return _format_error("unpause_dag", e)
    return f"DAG '{dag_id}' is now unpaused."


@mcp.tool
async def get_connections(
    ddu: Annotated[str | None, "DDU instance code. Uses default if omitted."] = None,
) -> str:
    """List all Airflow connections with their type and host.

    Passwords are always masked by Airflow. Use this to verify connection
    config or diagnose 'connection not found' errors.

    Example: get_connections(ddu="eiga")
    """
    client = _client(ddu)
    try:
        data = await client.get("/connections")
    except Exception as e:
        return _format_error("get_connections", e)

    connections = _extract_list(data, "connections")
    lines = []
    for conn in connections:
        lines.append(
            f"  {conn.get('connection_id', '?')} | "
            f"type={conn.get('conn_type', '?')} | "
            f"host={conn.get('host', '-')} | "
            f"port={conn.get('port', '-')}"
        )
    return f"Connections ({len(lines)}):\n" + "\n".join(lines) if lines else "No connections found."


@mcp.tool
async def get_task_instances(
    dag_id: Annotated[str, "The DAG ID"],
    run_id: Annotated[str, "The DAG run ID"],
    ddu: Annotated[str | None, "DDU instance code. Uses default if omitted."] = None,
) -> str:
    """List all task instances for a specific DAG run with their states.

    Shows each task's state (success, failed, running, etc.) and duration.
    Use this to find which tasks failed before fetching their logs.

    Example: get_task_instances(dag_id="etl_orders", run_id="scheduled__2026-04-13T00:00:00+00:00")
    """
    client = _client(ddu)
    try:
        data = await client.get(f"/dags/{dag_id}/dagRuns/{run_id}/taskInstances")
    except Exception as e:
        return _format_error("get_task_instances", e)

    tasks = _extract_list(data, "task_instances")
    lines = [f"Task instances for '{dag_id}' run '{run_id}' ({len(tasks)} tasks):"]
    for t in tasks:
        duration = f" ({t['duration']:.1f}s)" if t.get("duration") is not None else ""
        state_icon = {"success": "+", "failed": "X", "running": "~", "upstream_failed": "!"}.get(
            t.get("state", ""), "?"
        )
        lines.append(
            f"  [{state_icon}] {t.get('task_id', '?')} | "
            f"state={t.get('state', '?')}{duration} | "
            f"try={t.get('try_number', '?')}"
        )
    return "\n".join(lines)


@mcp.tool
async def diagnose_dag_run(
    dag_id: Annotated[str, "The DAG ID to diagnose"],
    run_id: Annotated[str | None, "The DAG run ID. If omitted, uses the most recent failed run."] = None,
    ddu: Annotated[str | None, "DDU instance code. Uses default if omitted."] = None,
) -> str:
    """Diagnose a DAG run: fetch run details, find failed tasks, and get their logs.

    This is a composite tool that replaces a 3-step workflow:
    1. get_dag_runs to find the run
    2. get_task_instances to find failed tasks
    3. get_task_logs for each failed task

    If run_id is omitted, automatically finds the most recent failed run.

    Example: diagnose_dag_run(dag_id="etl_orders", ddu="eiga")
    Example: diagnose_dag_run(dag_id="etl_orders", run_id="manual__2026-04-13T10:00:00+00:00")
    """
    track("diagnose_dag_run")
    client = _client(ddu)
    sections: list[str] = []

    if not run_id:
        try:
            runs_data = await client.get(
                f"/dags/{dag_id}/dagRuns",
                params={"limit": 1, "order_by": "-start_date", "state": "failed"},
            )
            runs = _extract_list(runs_data, "dag_runs")
            if not runs:
                return f"No failed runs found for DAG '{dag_id}'."
            run_id = runs[0].get("dag_run_id")
            sections.append(f"Most recent failed run: {run_id}")
            sections.append(_format_run(runs[0]))
        except Exception as e:
            return _format_error("diagnose_dag_run", e)

    try:
        ti_data = await client.get(f"/dags/{dag_id}/dagRuns/{run_id}/taskInstances")
    except Exception as e:
        return _format_error("diagnose_dag_run (task instances)", e)

    tasks = _extract_list(ti_data, "task_instances")
    failed_tasks = [t for t in tasks if t.get("state") == "failed"]
    total = len(tasks)
    succeeded = sum(1 for t in tasks if t.get("state") == "success")

    sections.append(f"\nTask summary: {total} total, {succeeded} succeeded, {len(failed_tasks)} failed")

    if not failed_tasks:
        for t in tasks:
            sections.append(f"  {t.get('task_id', '?')}: {t.get('state', '?')}")
        return "\n".join(sections)

    async def fetch_failed_log(task: dict) -> str:
        tid = task.get("task_id", "?")
        try_num = task.get("try_number", 1)
        try:
            log_text = await client.fetch_task_log(dag_id, run_id, tid, try_num)
        except Exception as exc:
            log_text = f"(could not fetch logs: {exc})"

        # Truncate long logs to last 80 lines to save tokens
        log_lines = log_text.strip().split("\n")
        if len(log_lines) > 80:
            log_text = f"... ({len(log_lines) - 80} lines truncated) ...\n" + "\n".join(log_lines[-80:])

        return f"\n--- Failed task: {tid} (try #{try_num}) ---\n{log_text}"

    log_results = await asyncio.gather(
        *(fetch_failed_log(t) for t in failed_tasks[:5])
    )
    sections.extend(log_results)

    if len(failed_tasks) > 5:
        sections.append(f"\n... and {len(failed_tasks) - 5} more failed tasks (use get_task_logs for individual logs)")

    return "\n".join(sections)


@mcp.tool
async def get_dag_overview(
    dag_id: Annotated[str, "The DAG ID"],
    num_runs: Annotated[int, "Number of recent runs to show"] = 5,
    ddu: Annotated[str | None, "DDU instance code. Uses default if omitted."] = None,
) -> str:
    """Get a comprehensive overview of a DAG: metadata plus recent run history.

    Combines DAG details (schedule, owner, tags, paused status) with recent
    run history in a single call. Use this as a starting point when investigating
    any DAG.

    Example: get_dag_overview(dag_id="etl_orders", ddu="eiga")
    """
    client = _client(ddu)

    try:
        dag_data, runs_data = await asyncio.gather(
            client.get(f"/dags/{dag_id}"),
            client.get(f"/dags/{dag_id}/dagRuns", params={"limit": num_runs, "order_by": "-start_date"}),
        )
    except Exception as e:
        return _format_error("get_dag_overview", e)

    lines = [f"DAG: {dag_id}"]
    lines.append(f"  Schedule: {dag_data.get('timetable_summary', dag_data.get('schedule_interval', '?'))}")
    lines.append(f"  Paused: {dag_data.get('is_paused', '?')}")
    lines.append(f"  Owner: {', '.join(dag_data.get('owners', ['?']))}")
    tags = dag_data.get("tags", [])
    if tags:
        tag_names = [t.get("name", t) if isinstance(t, dict) else t for t in tags]
        lines.append(f"  Tags: {', '.join(tag_names)}")
    lines.append(f"  File: {dag_data.get('fileloc', '?')}")

    runs = _extract_list(runs_data, "dag_runs")
    if runs:
        lines.append(f"\nRecent runs ({len(runs)}):")
        lines.extend(_format_run(r) for r in runs)
    else:
        lines.append("\nNo recent runs.")

    return "\n".join(lines)


@mcp.tool
async def morning_standup(
    ddu: Annotated[str | None, "DDU instance code. Uses default if omitted."] = None,
    dag_limit: Annotated[int, "Max DAGs to check"] = 100,
) -> str:
    """Your morning standup companion — one call to see everything that needs attention.

    Returns a combined view of:
    - DAGs with failed latest runs (needs fixing)
    - DAGs currently running (in progress)
    - Summary stats (total active, paused, healthy)

    Example: morning_standup(ddu="eiga")
    """
    track("morning_standup")
    client = _client(ddu)

    try:
        dags_data = await client.get("/dags", params={"limit": dag_limit, "only_active": "true"})
    except Exception as e:
        return _format_error("morning_standup", e)

    dags = _extract_list(dags_data, "dags")
    paused_count = sum(1 for d in dags if d.get("is_paused"))
    active_dags = [d for d in dags if d.get("dag_id") and not d.get("is_paused")]

    sem = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    results = await asyncio.gather(
        *(_check_latest_run(client, d["dag_id"], sem) for d in active_dags)
    )

    failing = []
    running = []
    for dag_id, state, run in results:
        if state == "failed" and run:
            failing.append(f"  {dag_id} | run={run.get('dag_run_id', '?')} | failed at {run.get('end_date', '?')}")
        elif state == "running" and run:
            running.append(f"  {dag_id} | run={run.get('dag_run_id', '?')} | started {run.get('start_date', '?')}")
        elif state.startswith("error:"):
            failing.append(f"  {dag_id} | {state}")

    healthy = len(results) - len(failing) - len(running)

    sections = [
        f"Morning Standup — {len(dags)} active DAGs ({paused_count} paused, {len(dags) - paused_count} unpaused)"
    ]

    if failing:
        sections.append(f"\nFailing ({len(failing)}):")
        sections.extend(failing)
    else:
        sections.append("\nNo failing DAGs.")

    if running:
        sections.append(f"\nCurrently running ({len(running)}):")
        sections.extend(running)

    sections.append(f"\nHealthy: {healthy} DAGs with successful latest run")

    return "\n".join(sections)


@mcp.tool
async def slack_standup(
    ddu: Annotated[str | None, "DDU instance code. Uses default if omitted."] = None,
    dag_limit: Annotated[int, "Max DAGs to check"] = 100,
) -> str:
    """Generate a Slack-ready standup message — paste directly into your team channel.

    Returns Slack mrkdwn formatted output with bold DAG names, bullet points,
    and a clean summary. Copy-paste ready, no editing needed.

    Example: slack_standup(ddu="eiga")
    """
    track("slack_standup")
    client = _client(ddu)

    try:
        dags_data = await client.get("/dags", params={"limit": dag_limit, "only_active": "true"})
    except Exception as e:
        return _format_error("slack_standup", e)

    dags = _extract_list(dags_data, "dags")
    paused_count = sum(1 for d in dags if d.get("is_paused"))
    active_dags = [d for d in dags if d.get("dag_id") and not d.get("is_paused")]

    sem = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    results = await asyncio.gather(
        *(_check_latest_run(client, d["dag_id"], sem) for d in active_dags)
    )

    failing = []
    running = []
    for dag_id, state, run in results:
        if state == "failed" and run:
            failing.append((dag_id, run))
        elif state == "running" and run:
            running.append((dag_id, run))

    healthy = len(results) - len(failing) - len(running)
    ddu_label = ddu or _get_config().default_ddu

    lines = [f":airflow: *Airflow Standup — {ddu_label}*"]

    if failing:
        lines.append(f"\n:red_circle: *Failing ({len(failing)})*")
        for dag_id, run in failing:
            lines.append(f"• *{dag_id}* — failed at {run.get('end_date', '?')}")
    else:
        lines.append("\n:large_green_circle: *No failing DAGs*")

    if running:
        lines.append(f"\n:hourglass_flowing_sand: *Running ({len(running)})*")
        for dag_id, run in running:
            lines.append(f"• *{dag_id}* — started {run.get('start_date', '?')}")

    lines.append(f"\n:chart_with_upwards_trend: {healthy} healthy · {paused_count} paused · {len(active_dags)} active")

    return "\n".join(lines)


@mcp.tool
async def alert_context(
    dag_id: Annotated[str, "The DAG ID from the alert/incident"],
    ddu: Annotated[str | None, "DDU instance code. Uses default if omitted."] = None,
) -> str:
    """Quick incident response — get everything you need to respond to an alert.

    When you get paged about a DAG, call this with just the dag_id. It returns:
    - DAG overview (schedule, owner, tags)
    - Latest failed run details
    - Failed task logs (auto-fetched)
    - Connection info if relevant

    Designed to replace the "open browser, navigate 5 pages" workflow
    with a single tool call.

    Example: alert_context(dag_id="etl_orders_daily", ddu="eiga")
    """
    track("alert_context")
    client = _client(ddu)
    sections: list[str] = [f"=== Alert Context: {dag_id} ==="]

    # DAG overview
    try:
        dag_data = await client.get(f"/dags/{dag_id}")
        sections.append(f"\nSchedule: {dag_data.get('timetable_summary', dag_data.get('schedule_interval', '?'))}")
        sections.append(f"Owner: {', '.join(dag_data.get('owners', ['?']))}")
        sections.append(f"Paused: {dag_data.get('is_paused', '?')}")
        tags = dag_data.get("tags", [])
        if tags:
            tag_names = [t.get("name", t) if isinstance(t, dict) else t for t in tags]
            sections.append(f"Tags: {', '.join(tag_names)}")
    except Exception as e:
        sections.append(f"\nDAG details: {_format_error('get_dag', e)}")

    # Diagnosis (reuses diagnose_dag_run logic)
    sections.append("\n--- Diagnosis ---")
    diagnosis = await diagnose_dag_run(dag_id, ddu=ddu)
    sections.append(diagnosis)

    return "\n".join(sections)


@mcp.tool
async def get_team_dags(
    team: Annotated[str, "Team prefix to filter DAGs by, e.g. 'identity', 'logistics', 'payments'"],
    ddu: Annotated[str | None, "DDU instance code. Uses default if omitted."] = None,
    limit: Annotated[int, "Max DAGs to return"] = 100,
) -> str:
    """List DAGs owned by a specific team (filtered by DAG ID prefix or owner tag).

    DH DAGs often follow naming conventions like {team}_{domain}_{action}.
    This tool filters DAGs matching the team prefix in the dag_id or owner field.

    Example: get_team_dags(team="identity", ddu="eiga")
    """
    track("get_team_dags")
    client = _client(ddu)

    try:
        data = await client.get("/dags", params={"limit": limit, "only_active": "true"})
    except Exception as e:
        return _format_error("get_team_dags", e)

    dags = _extract_list(data, "dags")
    team_lower = team.lower()

    matched = []
    for dag in dags:
        dag_id = dag.get("dag_id", "")
        owners = dag.get("owners", [])
        tags = dag.get("tags", [])
        tag_names = [t.get("name", t) if isinstance(t, dict) else t for t in tags]

        if (
            dag_id.lower().startswith(team_lower)
            or any(team_lower in o.lower() for o in owners)
            or any(team_lower in t.lower() for t in tag_names)
        ):
            status = "paused" if dag.get("is_paused") else "active"
            matched.append(f"  {dag_id} | owner={', '.join(owners)} | {status}")

    if not matched:
        return f"No DAGs found matching team '{team}'."
    return f"DAGs for team '{team}' ({len(matched)}):\n" + "\n".join(matched)


@mcp.tool
async def usage_stats() -> str:
    """Show usage statistics for this MCP server (local-only tracking).

    Enable tracking with AIRFLOW_MCP_TRACK_USAGE=1 in your environment.
    All data is stored locally, no telemetry.

    Example: usage_stats()
    """
    from .usage import get_stats
    return get_stats()


@mcp.prompt
def troubleshoot_failing_dag(dag_id: str, ddu: str = "") -> str:
    """Step-by-step workflow to diagnose and fix a failing DAG.

    Use this prompt when a user reports a DAG is failing and you need to
    investigate. It guides you through the diagnosis workflow.
    """
    ddu_arg = f', ddu="{ddu}"' if ddu else ""
    return f"""I need to troubleshoot the failing DAG '{dag_id}'. Follow these steps:

1. First, get an overview of the DAG to understand what it does:
   Call: get_dag_overview(dag_id="{dag_id}"{ddu_arg})

2. Then diagnose the most recent failed run (this fetches failed tasks + logs automatically):
   Call: diagnose_dag_run(dag_id="{dag_id}"{ddu_arg})

3. Based on the error logs, determine the root cause. Common patterns:
   - Connection errors → check get_connections() for misconfigured connections
   - Permission denied → auth issue, likely needs DH platform team
   - Data quality errors → upstream data issue, check the source DAG
   - OOM / timeout → resource issue, may need DAG config change
   - Import errors → code deployment issue

4. If the fix is clear, suggest it. If the DAG needs to be re-run after fixing:
   Call: trigger_dag(dag_id="{dag_id}"{ddu_arg})

5. If the DAG is creating alert storms while you investigate:
   Call: pause_dag(dag_id="{dag_id}"{ddu_arg})
   Remember to unpause it after fixing!
"""


@mcp.prompt
def daily_health_check(ddu: str = "") -> str:
    """Morning health check workflow for Airflow instances.

    Use this prompt to run a comprehensive health check at the start of the day.
    """
    ddu_arg = f', ddu="{ddu}"' if ddu else ""
    return f"""Run the morning health check for Airflow. Follow these steps:

1. Get the full standup view (failing + running + stats):
   Call: morning_standup({f'ddu="{ddu}"' if ddu else ''})

2. For each failing DAG in the output, diagnose it:
   Call: diagnose_dag_run(dag_id="<dag_id>"{ddu_arg})

3. Summarize findings for the standup:
   - Which DAGs are broken and why
   - Which are currently running (expected or stuck?)
   - Any action items (re-trigger, pause, escalate to platform team)

4. If any DAGs need immediate re-runs:
   Call: trigger_dag(dag_id="<dag_id>"{ddu_arg})
"""


def main():
    mcp.run()


if __name__ == "__main__":
    main()
