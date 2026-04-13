"""Configuration loading and DDU instance resolution."""

from __future__ import annotations

import os
from dataclasses import dataclass
from importlib.metadata import version as pkg_version
from pathlib import Path

import yaml

from .auth import AuthProvider, create_auth_provider

CONFIG_SEARCH_PATHS = [
    Path.cwd() / "config.yaml",
    Path.home() / ".config" / "airflow-mcp" / "config.yaml",
]


def get_version() -> str:
    try:
        return pkg_version("airflow-mcp-server")
    except Exception:
        return "0.1.0-dev"


@dataclass
class AirflowInstance:
    """A resolved Airflow instance with its base URL and auth."""

    ddu: str
    base_url: str
    auth: AuthProvider


class ConfigError(Exception):
    """Raised when config is missing or invalid."""


class Config:
    """Manages DDU -> AirflowInstance mapping.

    Config file is searched in this order:
    1. AIRFLOW_MCP_CONFIG env var (explicit path override)
    2. ./config.yaml (current working directory)
    3. ~/.config/airflow-mcp/config.yaml (user config)
    """

    def __init__(self, config_path: Path | None = None) -> None:
        path = config_path or self._find_config()
        raw = yaml.safe_load(path.read_text())

        if not isinstance(raw, dict):
            raise ConfigError(f"Config file {path} is not a valid YAML mapping")

        if "instances" not in raw or not raw["instances"]:
            raise ConfigError(
                f"Config file {path} has no 'instances' section. "
                "Each instance needs a base_url and auth block. See config.example.yaml."
            )

        self.default_ddu: str = raw.get("default_ddu", "local")
        self._instances: dict[str, AirflowInstance] = {}

        for ddu, inst_cfg in raw["instances"].items():
            if not isinstance(inst_cfg, dict):
                raise ConfigError(f"Instance '{ddu}' must be a mapping with base_url and auth")
            if "base_url" not in inst_cfg:
                raise ConfigError(f"Instance '{ddu}' is missing 'base_url'")
            if "auth" not in inst_cfg:
                raise ConfigError(f"Instance '{ddu}' is missing 'auth' section")

            base_url = inst_cfg["base_url"].rstrip("/")
            auth = create_auth_provider(inst_cfg["auth"])
            self._instances[ddu] = AirflowInstance(ddu=ddu, base_url=base_url, auth=auth)

        if self.default_ddu not in self._instances:
            available = ", ".join(sorted(self._instances.keys()))
            raise ConfigError(
                f"default_ddu '{self.default_ddu}' not found in instances. Available: {available}"
            )

    def resolve(self, ddu: str | None = None) -> AirflowInstance:
        """Resolve a DDU code to an AirflowInstance. Falls back to default."""
        key = ddu or self.default_ddu
        if key not in self._instances:
            available = ", ".join(sorted(self._instances.keys()))
            raise ValueError(f"Unknown DDU '{key}'. Available: {available}")
        return self._instances[key]

    @property
    def available_ddus(self) -> list[str]:
        return sorted(self._instances.keys())

    @property
    def instances_summary(self) -> dict[str, str]:
        """Return DDU -> base_url mapping (no auth details)."""
        return {ddu: inst.base_url for ddu, inst in sorted(self._instances.items())}

    @staticmethod
    def _find_config() -> Path:
        env_path = os.environ.get("AIRFLOW_MCP_CONFIG")
        if env_path:
            p = Path(env_path)
            if p.exists():
                return p
            raise FileNotFoundError(f"AIRFLOW_MCP_CONFIG points to {env_path} but file does not exist")

        for p in CONFIG_SEARCH_PATHS:
            if p.exists():
                return p

        raise FileNotFoundError(
            "No config.yaml found. Searched:\n"
            "  - AIRFLOW_MCP_CONFIG env var (not set)\n"
            + "\n".join(f"  - {p}" for p in CONFIG_SEARCH_PATHS)
            + "\nCopy config.example.yaml to one of those locations."
        )
