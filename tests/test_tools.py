"""Tests for MCP tool functions with mocked Airflow API responses.

Each test patches the module-level _config and _clients to inject a mock client,
then calls the tool function directly (bypassing MCP transport).
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
import respx

from airflow_mcp.auth import BasicAuthProvider
from airflow_mcp.client import AirflowClient
from airflow_mcp.config import AirflowInstance
from airflow_mcp import server as srv


@pytest.fixture(autouse=True)
def reset_server_state():
    """Reset module-level caches between tests."""
    srv._config = None
    srv._clients.clear()
    yield
    srv._config = None
    srv._clients.clear()


@pytest.fixture
def mock_setup():
    """Set up a mock client wired into the server module."""
    instance = AirflowInstance(
        ddu="test", base_url="http://airflow.test",
        auth=BasicAuthProvider("user", "pass"),
    )
    client = AirflowClient(instance)
    srv._clients["test"] = client

    # Make resolve always return our test instance
    class FakeConfig:
        default_ddu = "test"
        def resolve(self, ddu=None):
            return instance
        @property
        def available_ddus(self):
            return ["test"]
        @property
        def instances_summary(self):
            return {"test": "http://airflow.test"}

    srv._config = FakeConfig()
    return client


# --- get_task_logs ---

@pytest.mark.asyncio
async def test_get_task_logs_text(mock_setup):
    with respx.mock(base_url="http://airflow.test/api/v2") as router:
        router.get("/dags/my_dag/dagRuns/run1/taskInstances/task1/logs/1").respond(
            text="[2026-04-13] INFO - Task completed successfully"
        )
        result = await srv.get_task_logs("my_dag", "run1", "task1")
        assert "Task completed successfully" in result


@pytest.mark.asyncio
async def test_get_task_logs_json_fallback(mock_setup):
    with respx.mock(base_url="http://airflow.test/api/v2") as router:
        route = router.get("/dags/d/dagRuns/r/taskInstances/t/logs/1")
        route.side_effect = [
            httpx.Response(406, text="Not Acceptable"),
            httpx.Response(200, json={"content": "fallback log"}),
        ]
        result = await srv.get_task_logs("d", "r", "t")
        assert "fallback log" in result


@pytest.mark.asyncio
async def test_get_task_logs_error(mock_setup):
    with respx.mock(base_url="http://airflow.test/api/v2") as router:
        router.get("/dags/d/dagRuns/r/taskInstances/t/logs/1").respond(404)
        result = await srv.get_task_logs("d", "r", "t")
        assert "Error" in result


# --- get_dag_runs ---

@pytest.mark.asyncio
async def test_get_dag_runs(mock_setup):
    with respx.mock(base_url="http://airflow.test/api/v2") as router:
        router.get("/dags/etl/dagRuns").respond(json={
            "dag_runs": [
                {"dag_run_id": "run1", "state": "success", "start_date": "2026-04-13T00:00:00Z", "end_date": "2026-04-13T01:00:00Z"},
                {"dag_run_id": "run2", "state": "failed", "start_date": "2026-04-12T00:00:00Z", "end_date": "2026-04-12T00:30:00Z"},
            ]
        })
        result = await srv.get_dag_runs("etl")
        assert "run1" in result
        assert "run2" in result
        assert "success" in result


@pytest.mark.asyncio
async def test_get_dag_runs_with_state_filter(mock_setup):
    with respx.mock(base_url="http://airflow.test/api/v2") as router:
        router.get("/dags/etl/dagRuns").respond(json={
            "dag_runs": [
                {"dag_run_id": "run2", "state": "failed", "start_date": "2026-04-12T00:00:00Z", "end_date": "2026-04-12T00:30:00Z"},
            ]
        })
        result = await srv.get_dag_runs("etl", state="failed")
        assert "(state=failed)" in result
        assert "run2" in result


@pytest.mark.asyncio
async def test_get_dag_runs_empty(mock_setup):
    with respx.mock(base_url="http://airflow.test/api/v2") as router:
        router.get("/dags/etl/dagRuns").respond(json={"dag_runs": []})
        result = await srv.get_dag_runs("etl")
        assert "No runs found" in result


# --- get_failing_dags ---

@pytest.mark.asyncio
async def test_get_failing_dags_mixed(mock_setup):
    with respx.mock(base_url="http://airflow.test/api/v2") as router:
        router.get("/dags").respond(json={
            "dags": [
                {"dag_id": "healthy_dag", "is_paused": False},
                {"dag_id": "broken_dag", "is_paused": False},
            ]
        })
        router.get("/dags/healthy_dag/dagRuns").respond(json={
            "dag_runs": [{"dag_run_id": "r1", "state": "success", "end_date": "2026-04-13T01:00:00Z"}]
        })
        router.get("/dags/broken_dag/dagRuns").respond(json={
            "dag_runs": [{"dag_run_id": "r2", "state": "failed", "end_date": "2026-04-13T00:30:00Z"}]
        })
        result = await srv.get_failing_dags()
        assert "broken_dag" in result
        assert "healthy_dag" not in result
        assert "Failing DAGs (1)" in result


@pytest.mark.asyncio
async def test_get_failing_dags_all_clear(mock_setup):
    with respx.mock(base_url="http://airflow.test/api/v2") as router:
        router.get("/dags").respond(json={
            "dags": [{"dag_id": "ok_dag", "is_paused": False}]
        })
        router.get("/dags/ok_dag/dagRuns").respond(json={
            "dag_runs": [{"dag_run_id": "r1", "state": "success", "end_date": "2026-04-13T01:00:00Z"}]
        })
        result = await srv.get_failing_dags()
        assert "All clear" in result


# --- trigger_dag ---

@pytest.mark.asyncio
async def test_trigger_dag(mock_setup):
    with respx.mock(base_url="http://airflow.test/api/v2") as router:
        router.post("/dags/etl/dagRuns").respond(json={"dag_run_id": "manual__123", "state": "queued"})
        result = await srv.trigger_dag("etl")
        assert "manual__123" in result
        assert "queued" in result


@pytest.mark.asyncio
async def test_trigger_dag_with_conf(mock_setup):
    with respx.mock(base_url="http://airflow.test/api/v2") as router:
        router.post("/dags/etl/dagRuns").respond(json={"dag_run_id": "manual__456", "state": "queued"})
        result = await srv.trigger_dag("etl", conf='{"date": "2026-04-12"}')
        assert "manual__456" in result


@pytest.mark.asyncio
async def test_trigger_dag_invalid_conf(mock_setup):
    result = await srv.trigger_dag("etl", conf="not json")
    assert "Invalid JSON" in result


# --- pause / unpause ---

@pytest.mark.asyncio
async def test_pause_dag(mock_setup):
    with respx.mock(base_url="http://airflow.test/api/v2") as router:
        router.patch("/dags/etl").respond(json={"is_paused": True})
        result = await srv.pause_dag("etl")
        assert "paused" in result


@pytest.mark.asyncio
async def test_unpause_dag(mock_setup):
    with respx.mock(base_url="http://airflow.test/api/v2") as router:
        router.patch("/dags/etl").respond(json={"is_paused": False})
        result = await srv.unpause_dag("etl")
        assert "unpaused" in result


# --- get_connections ---

@pytest.mark.asyncio
async def test_get_connections(mock_setup):
    with respx.mock(base_url="http://airflow.test/api/v2") as router:
        router.get("/connections").respond(json={
            "connections": [
                {"connection_id": "pg_main", "conn_type": "postgres", "host": "db.example.com", "port": 5432},
                {"connection_id": "s3_data", "conn_type": "aws", "host": "", "port": None},
            ]
        })
        result = await srv.get_connections()
        assert "pg_main" in result
        assert "s3_data" in result
        assert "Connections (2)" in result


# --- get_task_instances ---

@pytest.mark.asyncio
async def test_get_task_instances(mock_setup):
    with respx.mock(base_url="http://airflow.test/api/v2") as router:
        router.get("/dags/etl/dagRuns/run1/taskInstances").respond(json={
            "task_instances": [
                {"task_id": "extract", "state": "success", "duration": 45.2, "try_number": 1},
                {"task_id": "load", "state": "failed", "duration": 12.1, "try_number": 2},
            ]
        })
        result = await srv.get_task_instances("etl", "run1")
        assert "[+] extract" in result
        assert "[X] load" in result
        assert "45.2s" in result


# --- diagnose_dag_run ---

@pytest.mark.asyncio
async def test_diagnose_dag_run_auto_find(mock_setup):
    with respx.mock(base_url="http://airflow.test/api/v2") as router:
        # Find latest failed run
        router.get("/dags/etl/dagRuns").respond(json={
            "dag_runs": [{"dag_run_id": "failed_run", "state": "failed",
                          "start_date": "2026-04-13T00:00:00Z", "end_date": "2026-04-13T00:30:00Z"}]
        })
        # Get task instances
        router.get("/dags/etl/dagRuns/failed_run/taskInstances").respond(json={
            "task_instances": [
                {"task_id": "good_task", "state": "success", "try_number": 1},
                {"task_id": "bad_task", "state": "failed", "try_number": 1},
            ]
        })
        # Get logs for failed task
        router.get("/dags/etl/dagRuns/failed_run/taskInstances/bad_task/logs/1").respond(
            text="ERROR: Connection refused to database"
        )
        result = await srv.diagnose_dag_run("etl")
        assert "failed_run" in result
        assert "2 total, 1 succeeded, 1 failed" in result
        assert "Connection refused" in result


@pytest.mark.asyncio
async def test_diagnose_dag_run_no_failures(mock_setup):
    with respx.mock(base_url="http://airflow.test/api/v2") as router:
        router.get("/dags/etl/dagRuns").respond(json={"dag_runs": []})
        result = await srv.diagnose_dag_run("etl")
        assert "No failed runs" in result


# --- get_dag_overview ---

@pytest.mark.asyncio
async def test_get_dag_overview(mock_setup):
    with respx.mock(base_url="http://airflow.test/api/v2") as router:
        router.get("/dags/etl").respond(json={
            "dag_id": "etl",
            "timetable_summary": "0 8 * * *",
            "is_paused": False,
            "owners": ["data-team"],
            "tags": [{"name": "production"}],
            "fileloc": "/opt/airflow/dags/etl.py",
        })
        router.get("/dags/etl/dagRuns").respond(json={
            "dag_runs": [
                {"dag_run_id": "run1", "state": "success", "start_date": "2026-04-13T08:00:00Z", "end_date": "2026-04-13T08:30:00Z"},
            ]
        })
        result = await srv.get_dag_overview("etl")
        assert "DAG: etl" in result
        assert "0 8 * * *" in result
        assert "data-team" in result
        assert "production" in result
        assert "run1" in result


# --- morning_standup ---

@pytest.mark.asyncio
async def test_morning_standup(mock_setup):
    with respx.mock(base_url="http://airflow.test/api/v2") as router:
        router.get("/dags").respond(json={
            "dags": [
                {"dag_id": "ok_dag", "is_paused": False},
                {"dag_id": "broken_dag", "is_paused": False},
                {"dag_id": "running_dag", "is_paused": False},
                {"dag_id": "paused_dag", "is_paused": True},
            ]
        })
        router.get("/dags/ok_dag/dagRuns").respond(json={
            "dag_runs": [{"dag_run_id": "r1", "state": "success", "start_date": "2026-04-13T00:00:00Z", "end_date": "2026-04-13T01:00:00Z"}]
        })
        router.get("/dags/broken_dag/dagRuns").respond(json={
            "dag_runs": [{"dag_run_id": "r2", "state": "failed", "start_date": "2026-04-13T00:00:00Z", "end_date": "2026-04-13T00:30:00Z"}]
        })
        router.get("/dags/running_dag/dagRuns").respond(json={
            "dag_runs": [{"dag_run_id": "r3", "state": "running", "start_date": "2026-04-13T08:00:00Z", "end_date": None}]
        })

        result = await srv.morning_standup()
        assert "Morning Standup" in result
        assert "broken_dag" in result
        assert "running_dag" in result
        assert "Failing (1)" in result
        assert "Currently running (1)" in result
        assert "Healthy: 1" in result
        assert "1 paused" in result


# --- slack_standup ---

@pytest.mark.asyncio
async def test_slack_standup(mock_setup):
    with respx.mock(base_url="http://airflow.test/api/v2") as router:
        router.get("/dags").respond(json={
            "dags": [
                {"dag_id": "ok_dag", "is_paused": False},
                {"dag_id": "broken_dag", "is_paused": False},
            ]
        })
        router.get("/dags/ok_dag/dagRuns").respond(json={
            "dag_runs": [{"dag_run_id": "r1", "state": "success", "start_date": "2026-04-13T00:00:00Z", "end_date": "2026-04-13T01:00:00Z"}]
        })
        router.get("/dags/broken_dag/dagRuns").respond(json={
            "dag_runs": [{"dag_run_id": "r2", "state": "failed", "start_date": "2026-04-13T00:00:00Z", "end_date": "2026-04-13T00:30:00Z"}]
        })
        result = await srv.slack_standup()
        # Verify Slack formatting
        assert ":airflow:" in result
        assert "*broken_dag*" in result
        assert ":red_circle:" in result
        assert ":chart_with_upwards_trend:" in result


# --- alert_context ---

@pytest.mark.asyncio
async def test_alert_context(mock_setup):
    with respx.mock(base_url="http://airflow.test/api/v2") as router:
        # DAG overview
        router.get("/dags/etl").respond(json={
            "dag_id": "etl",
            "timetable_summary": "0 8 * * *",
            "is_paused": False,
            "owners": ["data-team"],
            "tags": [],
        })
        # diagnose_dag_run internals
        router.get("/dags/etl/dagRuns").respond(json={
            "dag_runs": [{"dag_run_id": "fr1", "state": "failed",
                          "start_date": "2026-04-13T00:00:00Z", "end_date": "2026-04-13T00:30:00Z"}]
        })
        router.get("/dags/etl/dagRuns/fr1/taskInstances").respond(json={
            "task_instances": [
                {"task_id": "load", "state": "failed", "try_number": 1},
            ]
        })
        router.get("/dags/etl/dagRuns/fr1/taskInstances/load/logs/1").respond(
            text="ERROR: table not found"
        )
        result = await srv.alert_context("etl")
        assert "Alert Context: etl" in result
        assert "0 8 * * *" in result
        assert "data-team" in result
        assert "table not found" in result


# --- get_team_dags ---

@pytest.mark.asyncio
async def test_get_team_dags(mock_setup):
    with respx.mock(base_url="http://airflow.test/api/v2") as router:
        router.get("/dags").respond(json={
            "dags": [
                {"dag_id": "identity_user_sync", "owners": ["identity-team"], "tags": [], "is_paused": False},
                {"dag_id": "payments_daily", "owners": ["payments"], "tags": [], "is_paused": False},
                {"dag_id": "identity_audit", "owners": ["identity-team"], "tags": [{"name": "identity"}], "is_paused": True},
            ]
        })
        result = await srv.get_team_dags("identity")
        assert "identity_user_sync" in result
        assert "identity_audit" in result
        assert "payments_daily" not in result
        assert "DAGs for team 'identity' (2)" in result


@pytest.mark.asyncio
async def test_get_team_dags_no_match(mock_setup):
    with respx.mock(base_url="http://airflow.test/api/v2") as router:
        router.get("/dags").respond(json={
            "dags": [{"dag_id": "unrelated", "owners": ["other"], "tags": [], "is_paused": False}]
        })
        result = await srv.get_team_dags("identity")
        assert "No DAGs found" in result
