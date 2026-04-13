"""Tests for AirflowClient with mocked HTTP responses."""

import httpx
import pytest
import respx

from airflow_mcp.client import AirflowClient, _is_retryable
from airflow_mcp.config import AirflowInstance
from airflow_mcp.auth import BasicAuthProvider


@pytest.fixture
def instance() -> AirflowInstance:
    return AirflowInstance(
        ddu="test",
        base_url="http://airflow.test",
        auth=BasicAuthProvider("user", "pass"),
    )


@pytest.fixture
def client(instance: AirflowInstance) -> AirflowClient:
    return AirflowClient(instance)


@pytest.mark.asyncio
async def test_get_json(client: AirflowClient):
    with respx.mock(base_url="http://airflow.test/api/v2") as router:
        router.get("/dags").respond(json={"dags": [{"dag_id": "test_dag"}]})
        result = await client.get("/dags")
        assert result == {"dags": [{"dag_id": "test_dag"}]}


@pytest.mark.asyncio
async def test_post_json(client: AirflowClient):
    with respx.mock(base_url="http://airflow.test/api/v2") as router:
        router.post("/dags/test/dagRuns").respond(json={"dag_run_id": "run1", "state": "queued"})
        result = await client.post("/dags/test/dagRuns", json={"conf": {}})
        assert result["dag_run_id"] == "run1"


@pytest.mark.asyncio
async def test_patch_json(client: AirflowClient):
    with respx.mock(base_url="http://airflow.test/api/v2") as router:
        router.patch("/dags/test").respond(json={"is_paused": True})
        result = await client.patch("/dags/test", json={"is_paused": True})
        assert result["is_paused"] is True


@pytest.mark.asyncio
async def test_get_text(client: AirflowClient):
    with respx.mock(base_url="http://airflow.test/api/v2") as router:
        router.get("/dags/d/dagRuns/r/taskInstances/t/logs/1").respond(text="log line 1\nlog line 2")
        result = await client.get_text("/dags/d/dagRuns/r/taskInstances/t/logs/1")
        assert "log line 1" in result


@pytest.mark.asyncio
async def test_fetch_task_log_text(client: AirflowClient):
    with respx.mock(base_url="http://airflow.test/api/v2") as router:
        router.get("/dags/d/dagRuns/r/taskInstances/t/logs/1").respond(text="task output here")
        result = await client.fetch_task_log("d", "r", "t", 1)
        assert result == "task output here"


@pytest.mark.asyncio
async def test_fetch_task_log_json_fallback(client: AirflowClient):
    with respx.mock(base_url="http://airflow.test/api/v2") as router:
        # First call (text/plain) returns 406, second (JSON) succeeds
        route = router.get("/dags/d/dagRuns/r/taskInstances/t/logs/1")
        route.side_effect = [
            httpx.Response(406, text="Not Acceptable"),
            httpx.Response(200, json={"content": "json log content"}),
        ]
        result = await client.fetch_task_log("d", "r", "t", 1)
        assert result == "json log content"


@pytest.mark.asyncio
async def test_retry_on_503(client: AirflowClient):
    with respx.mock(base_url="http://airflow.test/api/v2") as router:
        route = router.get("/dags")
        route.side_effect = [
            httpx.Response(503, text="Service Unavailable"),
            httpx.Response(200, json={"dags": []}),
        ]
        result = await client.get("/dags")
        assert result == {"dags": []}
        assert route.call_count == 2


@pytest.mark.asyncio
async def test_no_retry_on_404(client: AirflowClient):
    with respx.mock(base_url="http://airflow.test/api/v2") as router:
        router.get("/dags/missing").respond(404, json={"detail": "not found"})
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await client.get("/dags/missing")
        assert exc_info.value.response.status_code == 404


def test_is_retryable_503():
    resp = httpx.Response(503)
    exc = httpx.HTTPStatusError("", request=httpx.Request("GET", "http://x"), response=resp)
    assert _is_retryable(exc) is True


def test_is_retryable_404():
    resp = httpx.Response(404)
    exc = httpx.HTTPStatusError("", request=httpx.Request("GET", "http://x"), response=resp)
    assert _is_retryable(exc) is False


def test_is_retryable_non_http():
    assert _is_retryable(ValueError("nope")) is False
