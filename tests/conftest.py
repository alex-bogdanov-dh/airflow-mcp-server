"""Shared test fixtures — mock AirflowClient backed by respx."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest
import respx

from airflow_mcp.auth import BasicAuthProvider
from airflow_mcp.client import AirflowClient
from airflow_mcp.config import AirflowInstance, Config


@pytest.fixture
def mock_instance() -> AirflowInstance:
    return AirflowInstance(
        ddu="test",
        base_url="http://airflow.test",
        auth=BasicAuthProvider("user", "pass"),
    )


@pytest.fixture
def mock_client(mock_instance: AirflowInstance) -> AirflowClient:
    return AirflowClient(mock_instance)


@pytest.fixture
def mock_router() -> respx.MockRouter:
    """respx mock router scoped to the Airflow base URL."""
    with respx.mock(base_url="http://airflow.test/api/v2") as router:
        yield router


@pytest.fixture
def tmp_config(tmp_path: Path) -> Path:
    """Write a minimal valid config file and return its path."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(dedent("""\
        default_ddu: local
        instances:
          local:
            base_url: "http://localhost:8080"
            auth:
              type: basic
              username: airflow
              password: airflow
    """))
    return cfg
