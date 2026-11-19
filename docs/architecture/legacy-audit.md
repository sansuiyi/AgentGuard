# AgentGuard 仓库审计报告（Phase 0）

> 审计日期：2026-11-18。本报告只记录**实际读过**的文件与真实调用关系，未读文件一律不写为“已审计”。
> 结论标记：KEEP（保留）/ REFACTOR（小步重构）/ MOVE（迁移）/ REPLACE（新实现替代）/ NEW（新增）。

## 1. 仓库性质与版本

- 仓库：`sansuiyi/AgentGuard`，基于开源 PR-Agent（Apache-2.0）二次开发，`pyproject.toml` 声明 `name = "pr-agent"`，`version = "0.47.0"`。
- Python 要求 `>=3.12`；实测 `.venv` 为 Python 3.12.7。
- 依赖管理：`uv`（`uv.lock`），`[tool.uv] required-version = ">=0.12.10"`。
- Lint：Ruff（`E/F/B/I`，line-length 120）；测试：pytest（`asyncio_mode=auto`，`testpaths=["tests/unittest"]`）。
- 当前分支 `main`，工作区存在大量未提交改动（`pr_agent/agent_exec/*`、`pr_agent/tools/pr_reviewer.py`、`pyproject.toml` 等已修改，`agentguard/`、`docs/AgentGuard技术设计与自动构建实施规范.md` 等未跟踪）。

## 2. 关键目录与入口

| 路径 | 职责 | 判定 |
|---|---|---|
| `pr_agent/cli.py` | PR-Agent CLI 入口（`pr-agent` console script，`command2class` 分发） | KEEP（兼容层入口） |
| `pr_agent/agent/`、`pr_agent/tools/`、`pr_agent/algo/` | 上游 PR 审查管线（review/describe/improve 等） | KEEP（不做改动） |
| `pr_agent/agent_exec/` | 旧版“多 Agent 审查循环”（runner/graph/nodes/policy/models/llm/federation/benchmark/tools） | REFACTOR（价值在，但已在新包 `agentguard/` 重建，后续收敛） |
| `agentguard/` | 自研框架骨架 + 已实现的审查循环 | 见 §4 |
| `pr_agent/settings/configuration.toml`、`.secrets_template.toml` | Dynaconf 配置与密钥模板 | KEEP |
| `tests/unittest/`（200+）、`tests/e2e_tests/`、`tests/health_test/` | 测试体系 | KEEP |

## 3. `pr_agent/agent_exec/`（旧审查循环）

已读：`runner.py`、`graph.py`、`nodes.py`、`policy.py`、`models.py`、`llm.py`、`federation.py`、`benchmark.py`、`tools/base.py`。

- 基于 LangGraph 的 `orient → review → {tools|verify|finalize} → orient` 有界循环。
- `runner.py::ReviewAgentRunner` 是旧入口，被 `agentguard/orchestration/runner.py` 的 `ReviewAgentRunner` 同名替代（新包）。
- 判定：**REFACTOR**——通用 Runtime 已在新包重建，旧包保留以免破坏 `/review` 门控，MVP 阶段不动。

## 4. `agentguard/`（现有内容）

已读核心文件：

| 文件 | 内容 | 判定 |
|---|---|---|
| `agentguard/__init__.py` | 顶层重导出 `AgentState/AuditEvent/Decision/Finding/ReviewAgentRunner/...`，`import` 时立即加载审查循环 | REFACTOR（应改为惰性导入，避免 Demo CLI 拖入 `pr_agent` 依赖） |
| `agentguard/core/schemas.py` | 审查循环模型：`ToolStatus/ToolResult/RiskLevel/Finding/Decision/AuditEvent/TrajectoryStep/AgentState` | KEEP（审查域，与行为平台模型不冲突） |
| `agentguard/core/policy.py` | `AgentPolicy/FederationPolicy/WorkspacePolicy` + `load_*()`，依赖 `pr_agent.config_loader.get_settings` | KEEP（审查域） |
| `agentguard/core/llm.py` | `AgentLLM`，复用 `LiteLLMAIHandler` | KEEP（审查域） |
| `agentguard/orchestration/{runner,graph,nodes,state,federation}.py` | 审查 OODA 循环实现 | KEEP（审查域，后置复用） |
| `agentguard/evaluation/benchmark.py` | 审查 Benchmark 评分框架 | KEEP（审查域） |
| `agentguard/analysis/tools/*` | MCP 标准化工具（base/read_file/find_references/static_analysis/workspace_read） | KEEP（审查域） |
| 其余 `agentguard/*/__init__.py`（decision/runtime/tracing/verification/reporting/testing/storage/services/integrations/api/agents/*） | 空骨架，docstring 已指向行为平台目标 | NEW（待填充） |

## 5. 测试基线

- `tests/unittest/agent_exec`（审查循环相关）：**68 passed**（本机实测 `PYTHONPATH=. .venv\Scripts\python.exe -m pytest tests/unittest/agent_exec -q`）。
- 全量 `tests/unittest` 规模 200+ 文件，未在本次审计全量重跑（避免长时间占用）；行为平台新增测试将独立于该目录运行。

## 6. 复用结论（对行为平台）

| 现有能力 | 行为平台是否需要 | 处理 |
|---|---|---|
| `pr_agent` Dynaconf 配置 / LiteLLM / GitHub Provider | MVP 不需要（Demo 必须无外部 API） | 行为平台使用自建 YAML 配置，**不 import `pr_agent`** |
| `agentguard` 审查循环（OODA/benchmark/MCP） | 第二阶段接真实 Agent 时可选复用 | 保留，不被 MVP 破坏 |
| Pydantic v2、PyYAML、pytest、ruff | 需要 | 复用现有依赖 |

## 7. 主要风险

1. `agentguard/__init__.py` 顶层 eager import 审查循环，会拖入 `pr_agent`（dynaconf 加载 `.secrets.toml` 打印告警）。Demo CLI 需避免此路径——将顶层导入改为惰性，或让 CLI 不触发重导出。
2. 现有审查循环与行为平台同用 `agentguard` 命名空间，存在模块名语义重叠（如 `orchestration/runner.py`），需用**新文件名**（如 `orchestration/workflow.py`、`core/models.py`）避开冲突。
3. `pyproject.toml` 尚无 `agentguard` console script，需新增。
