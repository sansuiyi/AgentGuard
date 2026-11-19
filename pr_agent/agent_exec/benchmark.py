"""Compatibility shim: the scoring harness moved to ``agentguard.evaluation.benchmark``."""

from agentguard.evaluation.benchmark import (
    BenchmarkItem,
    BenchmarkReport,
    BenchmarkRunner,
    ItemResult,
    ScoringWeights,
    load_dataset,
)

__all__ = [
    "BenchmarkItem",
    "BenchmarkReport",
    "BenchmarkRunner",
    "ItemResult",
    "ScoringWeights",
    "load_dataset",
]
