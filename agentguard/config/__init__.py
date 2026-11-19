"""Configuration loading and schemas for the behavior-testing platform."""

from agentguard.config.loader import load_config
from agentguard.config.schemas import Config, DemoConfig, JudgeConfig, PolicyConfig

__all__ = ["Config", "DemoConfig", "JudgeConfig", "PolicyConfig", "load_config"]
