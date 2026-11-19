# AgentGuard 实施计划（Phase 0 输出）

> 与 `legacy-audit.md` 配套。所有“NEW”模块按本计划分阶段实现；KEEP 模块不动。

## 处置清单

| 项 | 判定 | 说明 |
|---|---|---|
| `pr_agent/` 全量 | KEEP | 上游兼容层，不动 |
| `pr_agent/agent_exec/` | REFACTOR(后置) | MVP 不动，Phase 6 收敛 |
| `agentguard/core/{schemas,policy,llm}.py` | KEEP | 审查域 |
| `agentguard/orchestration/{runner,graph,nodes,state,federation}.py` | KEEP | 审查域 |
| `agentguard/evaluation/benchmark.py` | KEEP | 审查域 |
| `agentguard/analysis/tools/*` | KEEP | 审查域 |
| `agentguard/__init__.py` | REFACTOR | 改为惰性导入，新增行为平台公开符号 |
| 行为平台各模块 | NEW | 见下 |

## 行为平台新增模块（`agentguard/` 内，与审查域隔离）

- `core/models.py` / `core/enums.py` / `core/errors.py` — 行为平台数据模型（TestCase/AgentTrace/EvaluationResult/RiskDecision）
- `config/loader.py` / `config/schemas.py` — YAML 配置加载（不依赖 Dynaconf/pr_agent）
- `dataset/{loader,validator,builder,registry}.py` — JSONL 加载/校验/统计/断言注册表
- `runtime/{adapter,demo_agent,fault_injection,version_runner}.py` — 确定性 Demo Agent + 故障注入 + Base/Candidate 双版本执行
- `tracing/{models,collector,store}.py` — Trace 采集与持久化
- `evaluation/{rule_evaluator,pairwise,aggregator,judge}.py` — 规则评估 + 相对回归 + 聚合 + 可选 Judge
- `decision/{risk_engine,merge_gate}.py` — 确定性风险决策（PASS/REVIEW/BLOCK/ERROR）
- `verification/risk_verifier.py` — 高风险复核（MVP 最小实现）
- `reporting/{json_report,html_report}.py` + `reporting/templates/` — JSON/HTML 报告
- `planning/{test_selector,test_planner}.py` — full/smoke/impact 选择
- `orchestration/workflow.py` — 行为测试流水线编排
- `cli.py` — `agentguard` CLI（`dataset`/`run`/`demo`）

## 数据与配置

- `datasets/golden/{memory,emotion,personality,safety,tool_state}.jsonl`（每类 60 条，共 300 条；默认 smoke 每类 10 条，共 50 条）
- `datasets/fault_injection/scenarios.yaml`、`datasets/manifest.yaml`、`datasets/README.md`
- `configs/{default,demo,capability_mapping}.yaml`

## 测试

- `tests/unittest/agentguard/` — 模型/加载器/校验器/断言注册表/规则评估器/风险引擎/报告序列化/配置加载
- `tests/integration/agentguard/` — 完整流水线 + 各故障场景
- `tests/e2e/` — CLI 端到端（demo 闭环 + 报告产物校验）

## 工程改动

- `pyproject.toml` 新增 `[project.scripts] agentguard = "agentguard.cli:main"`
- `.gitignore` 增加 `reports/`、`*.log`
- README 补全最短运行路径

## 执行顺序

1. Phase 1：模型 + 配置 + 数据集 + 校验器 + CLI `dataset`（验收 `dataset validate/stats`）
2. Phase 2：Demo Agent + Adapter + 双版本 Runtime + Trace（验收多轮记忆用例产出 Trace）
3. Phase 3：故障注入 + 规则评估 + Pairwise + 风险决策（验收 Clean 无误报、故障可检出、安全 BLOCK）
4. Phase 4：`run`/`demo` 命令 + JSON/HTML 报告（验收一条命令出报告）
5. Phase 5：可选 Judge（未配置不阻断）+ 高风险复核（最小实现）
6. 测试全量 + README 验证
