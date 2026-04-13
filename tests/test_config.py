"""Tests for config loading and validation."""

from pathlib import Path
from textwrap import dedent

import pytest

from airflow_mcp.config import Config, ConfigError


def test_load_valid_config(tmp_config: Path):
    cfg = Config(config_path=tmp_config)
    assert cfg.default_ddu == "local"
    assert "local" in cfg.available_ddus


def test_resolve_default(tmp_config: Path):
    cfg = Config(config_path=tmp_config)
    inst = cfg.resolve()
    assert inst.ddu == "local"
    assert inst.base_url == "http://localhost:8080"


def test_resolve_unknown_ddu(tmp_config: Path):
    cfg = Config(config_path=tmp_config)
    with pytest.raises(ValueError, match="Unknown DDU 'nonexistent'"):
        cfg.resolve("nonexistent")


def test_missing_instances(tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("default_ddu: local\n")
    with pytest.raises(ConfigError, match="no 'instances' section"):
        Config(config_path=cfg_file)


def test_missing_base_url(tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(dedent("""\
        default_ddu: local
        instances:
          local:
            auth:
              type: basic
              username: a
              password: b
    """))
    with pytest.raises(ConfigError, match="missing 'base_url'"):
        Config(config_path=cfg_file)


def test_missing_auth(tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(dedent("""\
        default_ddu: local
        instances:
          local:
            base_url: "http://localhost:8080"
    """))
    with pytest.raises(ConfigError, match="missing 'auth'"):
        Config(config_path=cfg_file)


def test_default_ddu_not_in_instances(tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(dedent("""\
        default_ddu: production
        instances:
          local:
            base_url: "http://localhost:8080"
            auth:
              type: basic
              username: a
              password: b
    """))
    with pytest.raises(ConfigError, match="default_ddu 'production' not found"):
        Config(config_path=cfg_file)


def test_instances_summary(tmp_config: Path):
    cfg = Config(config_path=tmp_config)
    summary = cfg.instances_summary
    assert summary == {"local": "http://localhost:8080"}


def test_env_var_config(tmp_config: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AIRFLOW_MCP_CONFIG", str(tmp_config))
    cfg = Config()
    assert cfg.default_ddu == "local"
