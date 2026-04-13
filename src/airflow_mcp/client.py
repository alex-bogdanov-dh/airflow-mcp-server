"""HTTP client for Airflow 3.x REST API v2."""

from __future__ import annotations

import json
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from .config import AirflowInstance

API_PREFIX = "/api/v2"

RETRYABLE_STATUS_CODES = {429, 502, 503}


def _is_retryable(exc: BaseException) -> bool:
    """Only retry on transient HTTP errors (429, 502, 503)."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_STATUS_CODES
    return False


class AirflowClient:
    """Thin httpx wrapper targeting Airflow 3.x /api/v2/ exclusively.

    Holds a persistent AsyncClient for connection reuse (keep-alive, pooling).
    Auth headers are injected per-request so cookie refreshes take effect
    without restarting the server. Transient errors (429, 502, 503) are retried
    with exponential backoff (3 attempts, max 10s total).
    """

    def __init__(self, instance: AirflowInstance, timeout: float = 30.0) -> None:
        self._instance = instance
        self._client = httpx.AsyncClient(
            base_url=f"{instance.base_url}{API_PREFIX}",
            timeout=timeout,
        )

    async def close(self) -> None:
        await self._client.aclose()

    def _headers(self, accept: str = "application/json") -> dict[str, str]:
        headers = self._instance.auth.get_headers()
        headers["Accept"] = accept
        return headers

    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        reraise=True,
    )
    async def _request(self, method: str, path: str, accept: str = "application/json", **kwargs: Any) -> httpx.Response:
        kwargs.setdefault("headers", self._headers(accept))
        resp = await self._client.request(method, path, **kwargs)
        resp.raise_for_status()
        return resp

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        resp = await self._request("GET", path, params=params)
        return resp.json()

    async def post(self, path: str, json: dict[str, Any] | None = None) -> Any:
        resp = await self._request("POST", path, json=json or {})
        return resp.json()

    async def patch(self, path: str, json: dict[str, Any] | None = None) -> Any:
        resp = await self._request("PATCH", path, json=json or {})
        return resp.json()

    async def get_text(self, path: str, params: dict[str, Any] | None = None) -> str:
        resp = await self._request("GET", path, params=params, accept="text/plain")
        return resp.text

    async def fetch_task_log(
        self, dag_id: str, run_id: str, task_id: str, try_number: int = 1,
    ) -> str:
        """Fetch task log with automatic format detection (text/plain -> JSON fallback)."""
        path = f"/dags/{dag_id}/dagRuns/{run_id}/taskInstances/{task_id}/logs/{try_number}"
        try:
            return await self.get_text(path, params={"full_content": "true"})
        except (httpx.HTTPStatusError, UnicodeDecodeError):
            data = await self.get(path, params={"full_content": "true"})
            if isinstance(data, dict) and "content" in data:
                return data["content"]
            return json.dumps(data, indent=2)
