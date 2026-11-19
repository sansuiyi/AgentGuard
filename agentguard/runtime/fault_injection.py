"""Fault-injection scenario loading.

Scenarios are declarative YAML: a name maps to the fault IDs to inject into the
candidate and the decision the demo run must produce. Each scenario's
``expected_decision`` is asserted by the demo command, so a regression that is
no longer detected fails the demo rather than just printing "detected".
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from agentguard.core.errors import ConfigError
from agentguard.runtime.demo_agent import ALL_FAULT_IDS


def load_scenarios(path: str | Path) -> dict[str, dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"fault scenarios file not found: {p}", context={"path": str(p)})
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    scenarios = data.get("scenarios", {})
    if not isinstance(scenarios, dict) or not scenarios:
        raise ConfigError(f"no scenarios defined in {p}", context={"path": str(p)})
    return scenarios


def resolve_fault_ids(scenario_name: str, scenarios: dict[str, dict[str, Any]]) -> list[str]:
    if scenario_name not in scenarios:
        raise ConfigError(
            f"unknown scenario {scenario_name!r}",
            context={"scenario": scenario_name, "available": sorted(scenarios)},
        )
    fault_ids = scenarios[scenario_name].get("fault_ids", [])
    unknown = [f for f in fault_ids if f not in ALL_FAULT_IDS]
    if unknown:
        raise ConfigError(f"unknown fault ids {unknown}", context={"fault_ids": unknown})
    return list(fault_ids)
