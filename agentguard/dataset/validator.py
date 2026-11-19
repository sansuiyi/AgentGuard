"""Golden dataset validation.

Checks format, required fields, uniqueness, category/priority/assertion/capability
legality, and rejects obvious real-credential or privacy patterns. Returns a
structured report rather than throwing on the first error, so one command can
surface every problem at once.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentguard.core.models import TestCase
from agentguard.dataset.loader import iter_category_files, load_jsonl
from agentguard.dataset.registry import ASSERTION_TYPES, CAPABILITIES, PRIORITY_NAMES

# Patterns that look like real credentials or obvious private data. The dataset
# is fictional by policy, so hitting any of these is a validation error.
_CREDENTIAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),  # loose JWT
    re.compile(r"1[3-9]\d{9}"),  # CN mobile number
    re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),  # email
]


@dataclass
class ValidationIssue:
    path: str
    line: int
    message: str


@dataclass
class ValidationReport:
    valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    case_count: int = 0
    category_counts: dict[str, int] = field(default_factory=dict)

    def add(self, path: str, line: int, message: str) -> None:
        self.issues.append(ValidationIssue(path=path, line=line, message=message))
        self.valid = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "case_count": self.case_count,
            "category_counts": self.category_counts,
            "issues": [i.__dict__ for i in self.issues],
        }


def _walk_strings(obj: Any) -> list[str]:
    """Collect every string value in a nested structure for pattern scanning."""
    found: list[str] = []
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        for v in obj.values():
            found.extend(_walk_strings(v))
    elif isinstance(obj, list):
        for v in obj:
            found.extend(_walk_strings(v))
    return found


def _find_sensitive(raw: dict) -> str | None:
    for s in _walk_strings(raw):
        for pat in _CREDENTIAL_PATTERNS:
            if pat.search(s):
                return f"possible credential/private data matched pattern {pat.pattern!r}: {s[:40]}..."
    return None


def validate_case(raw: dict, path: str, line: int, report: ValidationReport) -> TestCase | None:
    """Validate one raw case dict, appending issues to ``report`` and returning the model."""
    try:
        case = TestCase.model_validate(raw)
    except Exception as exc:  # pydantic ValidationError
        report.add(path, line, f"schema error: {exc}")
        return None

    # category must be a legal name (schema already enforces the enum).
    expected_category = Path(path).stem
    if case.category.value != expected_category:
        report.add(path, line, f"category {case.category.value!r} does not match file {expected_category!r}")

    if case.priority.value not in PRIORITY_NAMES:
        report.add(path, line, f"illegal priority {case.priority.value!r}")

    for assertion in case.assertions:
        if assertion.type not in ASSERTION_TYPES:
            report.add(path, line, f"unknown assertion type {assertion.type!r}")
        if assertion.type in {"emotion_state_equals", "emotion_state_in"} and (
            assertion.value is None and not assertion.values
        ):
            report.add(path, line, f"assertion {assertion.type!r} requires value/values")
        if assertion.type in {"tool_called", "tool_not_called", "tool_args_match", "tool_status_equals"} and (
            not assertion.tool_name
        ):
            report.add(path, line, f"assertion {assertion.type!r} requires tool_name")

    for capability in case.expected_capabilities:
        if capability not in CAPABILITIES:
            report.add(path, line, f"unknown capability {capability!r}")

    if case.priority.value in {"P0", "P1"} and not case.tags:
        report.add(path, line, f"{case.priority.value} case must declare a risk tag")

    sensitive = _find_sensitive(raw)
    if sensitive:
        report.add(path, line, sensitive)

    return case


def validate_dataset(dataset_dir: str | Path) -> ValidationReport:
    """Validate every category file, dedupe case ids, and count per category."""
    report = ValidationReport(valid=True)
    seen_ids: dict[str, tuple[str, int]] = {}

    for category, path in iter_category_files(dataset_dir):
        if not path.exists():
            report.add(str(path), 0, "missing category file")
            continue
        raw_records = load_jsonl(path)
        category_count = 0
        for line_no, raw in enumerate(raw_records, start=1):
            case = validate_case(raw, str(path), line_no, report)
            if case is None:
                continue
            category_count += 1
            report.case_count += 1
            if case.case_id in seen_ids:
                prev_path, prev_line = seen_ids[case.case_id]
                report.add(
                    str(path),
                    line_no,
                    f"duplicate case_id {case.case_id!r} (first seen {prev_path}:{prev_line})",
                )
            else:
                seen_ids[case.case_id] = (str(path), line_no)
        report.category_counts[category] = category_count

    if report.case_count == 0:
        report.valid = False
        report.add(str(dataset_dir), 0, "dataset contains zero valid cases")

    return report
