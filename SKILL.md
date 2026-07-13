---
name: aso
description: >
  Use this skill when the user wants to evolve, optimize, or auto-improve an existing OpenClaw
  skill based on production traces and test-driven deltas. Trigger it for skill diagnosis,
  TDO refactoring, delta-gated deployment, or turning failing traces into eval cases.
metadata: {"openclaw": {"emoji": "🚀"}}
---

# 🚀 ASO (Automatic Skill Optimizer)

全自动技能演化管道：从生产环境 Trace 到优化验证，结合 evolve 的实时诊断与 skill-opt 的 TDO 重构，实现“感知 → 诊断 → 生成 → 重构 → 量化 → 部署”闭环。

> 触发：当老板要求“优化技能”“诊断技能”“Trace 转测试用例”“自动演化 skill”“跑 ASO/evolve/skill-opt 流程”时，直接走本 skill。

---

## 入口

```python
from aso.orchestrate import run
result = run(target="planner", strategy="aso")
```

`strategy` 可选：`aso`（TDO 重构，默认）或 `bilevel`（4 轮 LLM 对话，兼容 evolve）。

---

## 5 步工作流

1. **Observe**：从 `sessions_history` 或 `state/trace_store.json` 采集 Trace（默认 100 条）
2. **Diagnose**：统计瓶颈，输出优先级报告
3. **Generate**：按策略生成候选方案
4. **Gate + Sandbox**：跑测试，计算 Delta，过门禁才放行
5. **Report & Deploy**：生成 Proposal，人工审批后原子写入

---

## 硬门禁

部署前必须满足以下任一条件：

- Δ Pass Rate ≥ +1%
- Δ Token ≤ -5%
- 或：Δ Pass Rate ≥ +5% 时允许 Token 小幅上升

不满足则直接拒绝，不进入 deploy。

---

## 安全边界

`evolution-policy.yaml` 定义可演化目标白名单，以下目标禁止自动修改：

- `runtime`、`gateway`、`scheduler`、`kernel`
- `evolution-policy.yaml`、`trace_schema.yaml`
- `openclaw.json`、`secret.json`
- `AGENTS.md`、`SOUL.md`、`USER.md`、`MEMORY.md`

部署失败自动回滚到上一个稳定版本。

---

## 详细配置与策略

见 `references/optimization-report.md`。
