"""HTTP client for Airflow 3.x REST API v2."""

from __future__ import annotations

from typing import Any

import httpx

from .config import AirflowInstance

API_PREFIX = "/api/v2"


class AirflowClient:
    """Thin httpx wrapper targeting Airflow 3.x /api/v2/ exclusively.

    Holds a persistent AsyncClient for connection reuse (keep-alive, pooling).
    """

    def __init__(self, instance: AirflowInstance, timeout: float = 30.0) -> None:
        self._instance = instance
        self._client = httpx.AsyncClient(
            base_url=f"{instance.base_url}{API_PREFIX}",
            headers={**instance.auth.get_headers(), "Accept": "application/json"},
            timeout=timeout,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
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
        resp = await self._client.request(
            "GET", path, params=params,
            headers={"Accept": "text/plain"},
        )
        resp.raise_for_status()
        return resp.text
