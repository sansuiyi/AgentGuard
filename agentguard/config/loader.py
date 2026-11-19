"""Configuration loading for the behavior-testing platform.

Priority: CLI overrides > environment variables > YAML profile > YAML default >
in-code defaults. Deliberately independent of Dynaconf / ``pr_agent`` so the
offline demo never needs API keys or upstream settings.
"""

from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from agentguard.config.schemas import Config
from agentguard.core.errors import ConfigError

# In-code defaults mirror ``configs/default.yaml``. Keeping them here means the
# loader still works when the YAML files are absent (e.g. packaged installs).
_DEFAULTS: dict[str, Any] = {
    "dataset_dir": "datasets/golden",
    "manifest_path": "datasets/manifest.yaml",
    "fault_scenarios_path": "datasets/fault_injection/scenarios.yaml",
    "capability_mapping_path": "configs/capability_mapping.yaml",
    "selection": "smoke",
    "output_dir": "reports",
    "seed": 42,
    "run_id_prefix": "run",
    "fault_ids": [],
    "categories": ["memory", "emotion", "personality", "safety", "tool_state"],
    "smoke_case_count_per_category": 10,
    "judge": {
        "enabled": False,
        "model": "",
        "temperature": 0.2,
        "timeout_seconds": 30.0,
        "max_retries": 1,
    },
    "policy": {
        "block_on_p0_safety": True,
        "block_on_confirmed_p1_regression": True,
        "p1_insufficient_evidence": "REVIEW",
        "p2_p3_noncritical": "REVIEW",
    },
    "demo": {
        "agent_name": "小守",
        "tone": "gentle",
        "base_latency_ms": 5.0,
    },
}

# Environment variables that may override config. Names are upper-snake and
# mapped to nested keys; only these are allowed so stray env vars never leak in.
_ENV_MAP: dict[str, str] = {
    "AGENTGUARD_DATASET_DIR": "dataset_dir",
    "AGENTGUARD_OUTPUT_DIR": "output_dir",
    "AGENTGUARD_SELECTION": "selection",
    "AGENTGUARD_SEED": "seed",
    "AGENTGUARD_JUDGE_ENABLED": "judge.enabled",
    "AGENTGUARD_JUDGE_MODEL": "judge.model",
}


def _load_yaml(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"config file not found: {p}", context={"path": str(p)})
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {p}: {exc}", context={"path": str(p)}) from exc
    if not isinstance(data, dict):
        raise ConfigError(f"config file must be a mapping: {p}", context={"path": str(p)})
    return data


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _set_nested(data: dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    node = data
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def _apply_env(data: dict[str, Any]) -> None:
    for env_key, dotted in _ENV_MAP.items():
        raw = os.environ.get(env_key)
        if raw is None or raw == "":
            continue
        if raw.isdigit():
            value: Any = int(raw)
        elif raw.lower() in {"true", "false"}:
            value = raw.lower() == "true"
        else:
            value = raw
        _set_nested(data, dotted, value)


def load_config(
    default_path: str | Path | None = None,
    profile_path: str | Path | None = None,
    overrides: dict[str, Any] | None = None,
) -> Config:
    """Build the effective config by layering defaults < files < env < overrides."""
    data: dict[str, Any] = deepcopy(_DEFAULTS)

    if default_path:
        data = _deep_merge(data, _load_yaml(default_path))
    if profile_path:
        data = _deep_merge(data, _load_yaml(profile_path))

    _apply_env(data)

    if overrides:
        data = _deep_merge(data, overrides)

    try:
        return Config.model_validate(data)
    except Exception as exc:  # pydantic ValidationError
        raise ConfigError(f"invalid configuration: {exc}") from exc
