---
name: aso
description: >
  Use this skill when the user wants to evolve, optimize, or auto-improve an existing OpenClaw
  skill based on production traces and test-driven deltas. Trigger it for skill diagnosis,
  TDO refactoring, delta-gated deployment, or converting failing traces into eval cases.
  Only trigger when the user explicitly mentions a skill name, trace/benchmark/delta,
  or uses phrases like "ASO", "evolve", "optimize skill".
metadata: {"openclaw": {"emoji": "🚀"}}
---

# 🚀 ASO (Automatic Skill Optimizer)

> 触发：当老板提到“优化技能 / 诊断技能 / Trace 转测试用例 / 自动演化 / ASO / evolve / skill-opt”，并且有以下任一强信号时再触发：
> - 给出 skill 名称或路径，如 planner / workflow / router
> - 提到 trace / benchmark / eval / delta / pass rate / token
> - 明确要求“跑 ASO / 走 evolve 流程 / 优化这个 skill”
>
> **NOT 触发条件**：普通闲聊、纯代码新建、知识问答、无技能名的模糊“优化”请求。

---

## 入口

```python
from aso.orchestrate import run
result = run(target="planner", strategy="aso")
```

`strategy`：`aso` 为默认策略（TDO 重构）；`bilevel` 为兼容 evolve 的 4 轮 LLM 策略。

---

## 5 步工作流

1. **Observe**：采集 Trace（默认 100 条）
2. **Diagnose**：输出瓶颈报告
3. **Generate**：按策略生成候选
4. **Gate + Sandbox**：验证 + 隔离评估 + **硬 Delta 门禁**
5. **Report & Deploy**：生成 Proposal，人工审批后原子写入

---

## 硬门禁

必须满足：

- Δ Pass Rate ≥ +1%
- Δ Token ≤ -5%
- 或：Δ Pass Rate ≥ +5% 且 Token 小幅上升

不满足 → 在 sandbox 阶段直接 `rejected`，不进 deploy。

---

## 安全边界

以 `evolution-policy.yaml` 为准，以下目标禁止自动修改：`runtime`、`gateway`、`scheduler`、`kernel`、`evolution-policy.yaml`、`trace_schema.yaml`、`openclaw.json`、`secret.json`、`AGENTS.md`、`SOUL.md`、`USER.md`、`MEMORY.md`。

失败自动回滚到上一个稳定版本。

---

## 详细说明

- CLI 契约：`docs/cli-contract.md`
- 触发器测试查询：`docs/trigger-tests.json`
