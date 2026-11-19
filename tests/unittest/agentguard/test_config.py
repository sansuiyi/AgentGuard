"""Unit tests for configuration loading and priority."""

from __future__ import annotations

import pytest

from agentguard.config.loader import load_config
from agentguard.core.errors import ConfigError


def test_defaults_are_populated() -> None:
    config = load_config()
    assert config.seed == 42
    assert config.dataset_dir == "datasets/golden"
    assert config.selection == "smoke"
    assert config.smoke_case_count_per_category == 10
    assert config.policy.block_on_p0_safety is True


def test_cli_overrides_win(tmp_path) -> None:
    config = load_config(overrides={"output_dir": str(tmp_path), "seed": 7})
    assert config.output_dir == str(tmp_path)
    assert config.seed == 7


def test_profile_overrides_default(tmp_path) -> None:
    profile = tmp_path / "profile.yaml"
    profile.write_text("selection: smoke\n", encoding="utf-8")
    config = load_config(profile_path=profile)
    assert config.selection == "smoke"


def test_env_override(monkeypatch) -> None:
    monkeypatch.setenv("AGENTGUARD_SELECTION", "risk_based")
    config = load_config()
    assert config.selection == "risk_based"
    monkeypatch.delenv("AGENTGUARD_SELECTION")


def test_missing_default_file_raises(tmp_path) -> None:
    with pytest.raises(ConfigError):
        load_config(default_path=tmp_path / "nope.yaml")


def test_invalid_config_value_raises(tmp_path) -> None:
    profile = tmp_path / "bad.yaml"
    profile.write_text("seed: not_an_int\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(profile_path=profile)
