# AgentGuard Golden 数据集

确定性、无外部依赖的行为回归测试集，覆盖陪伴类 Agent 的五大能力。

## 目录

- `golden/` — 五类 Golden 用例（每类 60 条，共 300 条），JSONL 格式（每行一条 JSON）。
- `fault_injection/scenarios.yaml` — 故障注入场景，每个场景注入一组 `FI-*` 故障并断言预期决策。
- `manifest.yaml` — 数据集清单（由 `agentguard dataset build` 生成）。

## 五类能力

| 类别 | 文件 | 说明 |
|---|---|---|
| 记忆 | `memory.jsonl` | 跨轮写入、召回、更正、遗忘、相似信息不混淆 |
| 情绪 | `emotion.jsonl` | 负面共情、状态更新、积极回应、愤怒安抚 |
| 人设 | `personality.jsonl` | 多轮一致、语气温柔、身份稳定、情绪场景不崩 |
| 安全 | `safety.jsonl` | 密码/验证码拦截、依赖诱导边界、自伤干预 |
| 工具 | `tool_state.jsonl` | 参数正确、超时如实、未授权拒绝、结果一致 |

## 运行方式

- 日常测试运行默认使用 `smoke` 选择：每类按优先级取 10 条，共 **50 条**（`configs/default.yaml`）。
- 需要全量回归时使用 `agentguard run --selection full`，运行全部 300 条。

## 校验与统计

```bash
agentguard dataset validate
agentguard dataset stats
agentguard dataset build
```

## 约定

- 所有用例均为**虚构**，不含真实凭据或隐私；校验器会拦截疑似真实凭据/手机号/邮箱格式。
- 每个用例 `assertions` 为机器可校验契约，断言类型见 `agentguard.dataset.registry.ASSERTION_TYPES`。
- `expected_capabilities` 取值必须存在于 `configs/capability_mapping.yaml`。
