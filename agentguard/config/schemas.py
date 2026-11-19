"""Configuration schema for the behavior-testing platform."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class JudgeConfig(BaseModel):
    """LLM-as-Judge settings. ``enabled=False`` keeps the demo offline."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    model: str = ""
    temperature: float = 0.2
    timeout_seconds: float = 30.0
    max_retries: int = 1


class PolicyConfig(BaseModel):
    """Deterministic risk-decision policy thresholds."""

    model_config = ConfigDict(extra="forbid")

    block_on_p0_safety: bool = True
    block_on_confirmed_p1_regression: bool = True
    p1_insufficient_evidence: str = "REVIEW"
    p2_p3_noncritical: str = "REVIEW"


class DemoConfig(BaseModel):
    """Deterministic demo agent personality."""

    model_config = ConfigDict(extra="forbid")

    agent_name: str = "小守"
    tone: str = "gentle"
    base_latency_ms: float = 5.0


class Config(BaseModel):
    """Top-level platform configuration."""

    model_config = ConfigDict(extra="forbid")

    dataset_dir: str = "datasets/golden"
    manifest_path: str = "datasets/manifest.yaml"
    fault_scenarios_path: str = "datasets/fault_injection/scenarios.yaml"
    capability_mapping_path: str = "configs/capability_mapping.yaml"
    selection: str = "smoke"
    output_dir: str = "reports"
    seed: int = 42
    run_id_prefix: str = "run"
    fault_ids: list[str] = Field(default_factory=list)
    categories: list[str] = Field(
        default_factory=lambda: ["memory", "emotion", "personality", "safety", "tool_state"]
    )
    smoke_case_count_per_category: int = 10
    judge: JudgeConfig = Field(default_factory=JudgeConfig)
    policy: PolicyConfig = Field(default_factory=PolicyConfig)
    demo: DemoConfig = Field(default_factory=DemoConfig)
