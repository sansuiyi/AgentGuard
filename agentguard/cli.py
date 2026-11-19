"""``agentguard`` command-line interface.

Subcommands: ``dataset`` (validate/stats/build/export-template), ``run``
(behavior regression run), ``demo`` (fault-injection scenarios). The CLI is
deliberately dependency-light (argparse + PyYAML) so it runs offline.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from agentguard.config.loader import load_config
from agentguard.config.schemas import Config
from agentguard.dataset.builder import build_manifest, export_template, stats
from agentguard.dataset.loader import load_dataset
from agentguard.dataset.validator import validate_dataset
from agentguard.orchestration.workflow import Workflow
from agentguard.planning.test_planner import plan
from agentguard.reporting.html_report import write_html
from agentguard.reporting.json_report import write_results_jsonl, write_summary
from agentguard.runtime.fault_injection import load_scenarios, resolve_fault_ids

_SELECTIONS = ("full", "smoke", "impact", "risk_based")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentguard", description="AgentGuard · GuardTest 行为回归测试平台")
    sub = parser.add_subparsers(dest="command", required=True)

    # ---- dataset ----
    dataset = sub.add_parser("dataset", help="管理 Golden 数据集")
    dsub = dataset.add_subparsers(dest="dataset_command", required=True)

    d_validate = dsub.add_parser("validate", help="校验数据集 schema 与合法性")
    d_validate.add_argument("--dataset-dir", default=None)

    d_stats = dsub.add_parser("stats", help="数据集统计")
    d_stats.add_argument("--dataset-dir", default=None)

    d_build = dsub.add_parser("build", help="从 JSONL 生成 manifest 并校验")
    d_build.add_argument("--dataset-dir", default=None)
    d_build.add_argument("--manifest", default=None)

    d_export = dsub.add_parser("export-template", help="导出单个用例模板")
    d_export.add_argument("--category", required=True)
    d_export.add_argument("--out", required=True)

    # ---- run ----
    run = sub.add_parser("run", help="运行行为回归测试（Base vs Candidate）")
    run.add_argument("--dataset-dir", default=None)
    run.add_argument("--selection", choices=_SELECTIONS, default=None)
    run.add_argument("--categories", nargs="*", default=None)
    run.add_argument("--fault-ids", nargs="*", default=None)
    run.add_argument("--output-dir", default=None)
    run.add_argument("--seed", type=int, default=None)
    run.add_argument("--run-id", default=None)

    # ---- demo ----
    demo = sub.add_parser("demo", help="运行故障注入演示场景")
    demo.add_argument("--scenario", default="clean")
    demo.add_argument("--list", action="store_true", help="列出所有场景")
    demo.add_argument("--dataset-dir", default=None)
    demo.add_argument("--output-dir", default=None)
    demo.add_argument("--run-id", default=None)

    return parser


def _config_from_args(args: argparse.Namespace) -> Config:
    overrides: dict[str, Any] = {}
    if getattr(args, "dataset_dir", None):
        overrides["dataset_dir"] = args.dataset_dir
    if getattr(args, "output_dir", None):
        overrides["output_dir"] = args.output_dir
    if getattr(args, "seed", None) is not None:
        overrides["seed"] = args.seed
    if getattr(args, "selection", None):
        overrides["selection"] = args.selection
    return load_config(
        default_path="configs/default.yaml",
        profile_path="configs/demo.yaml" if Path("configs/demo.yaml").exists() else None,
        overrides=overrides,
    )


def _make_run_id(prefix: str, seed: int, explicit: str | None) -> str:
    if explicit:
        return explicit
    return f"{prefix}-{seed}-{int(time.time())}"


def _write_reports(report: dict, output_dir: str) -> dict[str, str]:
    run_dir = Path(output_dir) / report["run_id"]
    summary_path = write_summary(report, run_dir / "summary.json")
    results_path = write_results_jsonl(report, run_dir / "results.jsonl")
    html_path = write_html(report, run_dir / "report.html")
    return {
        "summary": str(summary_path),
        "results": str(results_path),
        "html": str(html_path),
    }


def _print_summary(report: dict, artifact_paths: dict[str, str]) -> None:
    decision = report["decision"]
    aggregate = report["aggregate"]
    print(f"run_id: {report['run_id']}")
    print(f"decision: {decision['decision']}  ({decision['decision_reason']})")
    print(
        f"cases: {aggregate['total']} total, "
        f"{aggregate['candidate_passed']} passed, {len(aggregate['regressed'])} regressed"
    )
    print(f"report: {artifact_paths['html']}")
    print(f"summary: {artifact_paths['summary']}")


def _cmd_dataset(args: argparse.Namespace, config: Config) -> int:
    dataset_dir = args.dataset_dir or config.dataset_dir
    command = args.dataset_command

    if command == "validate":
        report = validate_dataset(dataset_dir)
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
        return 0 if report.valid else 1

    if command == "stats":
        print(json.dumps(stats(dataset_dir), ensure_ascii=False, indent=2))
        return 0

    if command == "build":
        manifest_path = args.manifest or config.manifest_path
        manifest = build_manifest(dataset_dir, manifest_path)
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0

    if command == "export-template":
        export_template(args.category, args.out)
        print(f"template written to {args.out}")
        return 0

    return 2


def _cmd_run(args: argparse.Namespace, config: Config) -> int:
    cases = load_dataset(config.dataset_dir)
    plan_result = plan(
        cases,
        args.selection or config.selection,
        categories=args.categories,
        smoke_count_per_category=config.smoke_case_count_per_category,
    )
    selected = plan_result["cases"]

    run_id = _make_run_id(config.run_id_prefix, config.seed, args.run_id)
    fault_ids = set(args.fault_ids or config.fault_ids or [])

    workflow = Workflow(config)
    report = workflow.run(selected, run_id=run_id, base_faults=set(), candidate_faults=fault_ids)
    artifacts = _write_reports(report, config.output_dir)
    _print_summary(report, artifacts)
    return 0


def _cmd_demo(args: argparse.Namespace, config: Config) -> int:
    scenarios = load_scenarios(config.fault_scenarios_path)

    if args.list:
        for name, scenario in scenarios.items():
            print(f"{name}: {scenario.get('description', '')}")
        return 0

    if args.scenario not in scenarios:
        print(f"unknown scenario {args.scenario!r}; available: {sorted(scenarios)}", file=sys.stderr)
        return 2

    scenario = scenarios[args.scenario]
    fault_ids = resolve_fault_ids(args.scenario, scenarios)
    expected_decision = scenario.get("expected_decision")

    cases = load_dataset(config.dataset_dir)
    selected = plan(
        cases,
        config.selection,
        smoke_count_per_category=config.smoke_case_count_per_category,
    )["cases"]
    run_id = _make_run_id(f"demo-{args.scenario}", config.seed, args.run_id)

    workflow = Workflow(config)
    report = workflow.run(selected, run_id=run_id, base_faults=set(), candidate_faults=set(fault_ids))
    artifacts = _write_reports(report, config.output_dir)
    _print_summary(report, artifacts)

    actual_decision = report["decision"]["decision"]
    if expected_decision and actual_decision != expected_decision:
        print(
            f"[FAIL] scenario {args.scenario!r}: expected {expected_decision}, got {actual_decision}",
            file=sys.stderr,
        )
        return 1

    print(f"[OK] scenario {args.scenario!r}: decision {actual_decision} (expected {expected_decision})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "dataset":
        config = _config_from_args(args)
        return _cmd_dataset(args, config)
    if args.command == "run":
        config = _config_from_args(args)
        return _cmd_run(args, config)
    if args.command == "demo":
        config = _config_from_args(args)
        return _cmd_demo(args, config)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
