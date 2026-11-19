"""Unit tests for behavior-platform data models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agentguard.core.models import TestCase


def _minimal() -> dict:
    return {
        "case_id": "MEM-1",
        "title": "t",
        "category": "memory",
        "user_profile": {"user_id": "u", "facts": []},
        "turns": [{"input": "hi"}],
        "assertions": [{"type": "response_contains", "text": "x"}],
    }


def test_minimal_case_is_valid() -> None:
    case = TestCase.model_validate(_minimal())
    assert case.case_id == "MEM-1"


def test_case_requires_assertions() -> None:
    data = _minimal()
    data["assertions"] = []
    with pytest.raises(ValidationError):
        TestCase.model_validate(data)


def test_case_requires_turns() -> None:
    data = _minimal()
    data["turns"] = []
    with pytest.raises(ValidationError):
        TestCase.model_validate(data)


def test_empty_case_id_rejected() -> None:
    data = _minimal()
    data["case_id"] = "   "
    with pytest.raises(ValidationError):
        TestCase.model_validate(data)


def test_unknown_field_rejected() -> None:
    data = _minimal()
    data["surprise"] = 1
    with pytest.raises(ValidationError):
        TestCase.model_validate(data)
