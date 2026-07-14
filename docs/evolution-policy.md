# Evolution Policy

> 日期：2026-07-14
> 定义 Delta 审批规则：哪些修改自动通过、哪些需要人工、哪些禁止。

---

## 设计原则

1. **安全优先** — 高风险操作必须人工审批
2. **渐进信任** — 同一 target 多次成功后可降低审批门槛
3. **策略可配置** — 不硬编码在代码中，通过 policy 文件控制

---

## 政策架构

```
Delta
  │
  ▼
Policy Engine
  │
  ├── auto_approve  ───→ Gate 直接通过
  ├── auto_reject   ───→ Gate 直接拒绝
  └── require_review ──→ 生成 Proposal，等人工审批
```

---

## 政策定义

存储位置：`state/evolution-policy.yaml`

```yaml
# state/evolution-policy.yaml
# 不可被 Evolution 自身修改

policy:
  # ─── 默认策略 ───
  default: require_review

  # ─── 按操作类型 ───
  by_operation_type:
    instruction_add:     auto_approve
    instruction_remove:  require_review
    instruction_modify:  require_review
    constraint_add:      auto_approve
    constraint_remove:   require_review
    constraint_modify:   require_review
    step_add:            require_review
    step_remove:         require_review
    step_modify:         require_review
    workflow_reorder:    require_review
    tool_call_add:       require_review
    tool_call_remove:    require_review
    tool_call_modify:    require_review

  # ─── 按风险等级 ───
  by_risk:
    low:    auto_approve
    medium: require_review
    high:   require_review

  # ─── 按 Target ───
  by_target:
    planner:  require_review
    router:   require_review
    workflow: require_review
    prompt:   auto_approve
    memory:   require_review
    skill:    require_review

  # ─── 禁止操作 ───
  deny:
    operations:
      - tool_call_remove    # 删除工具调用风险太大，永远禁止自动
    targets:
      - runtime
      - gateway
      - scheduler
      - kernel
      - openclaw.json
      - secret.json
      - AGENTS.md
      - SOUL.md
      - USER.md
      - MEMORY.md
      - evolution-policy.yaml
      - trace_schema.yaml

  # ─── 组合规则（多个条件同时满足） ───
  compound_rules:
    # 低风险 + 已信任 target = 自动通过
    - if:
        risk: low
        target: [planner, router]
        operation_type: [instruction_add, constraint_add]
      then: auto_approve

    # 高风险 + 首次优化 = 必须人工
    - if:
        risk: high
        session_count: 0
      then: require_review

    # 同一 target 连续 3 次成功部署后，审批降级
    - if:
        target: any
        consecutive_successes: ">= 3"
        risk: [low, medium]
      then: auto_approve
```

---

## 审批流程

```
Policy Engine 判定
       │
       │
       ├── auto_approve ────────────────────→ Gate 检查 → 部署
       │
       ├── auto_reject  ────────────────────→ 终止，记录原因
       │
       └── require_review ──→ 生成 Proposal
                  │
                  ├── 人工批准 ──→ Gate 检查 → 部署
                  │
                  └── 人工拒绝 ──→ 终止，记录原因
```

---

## 与 Evolution Session 的交互

```
session.started
  │
  ▼
diagnose + reflect
  │
  ▼
generate delta
  │
  ▼
Policy Engine evaluate(delta)
  │
  ├── auto_approve → session 标记 auto_approved
  │
  ├── auto_reject  → session 标记 rejected + 结束
  │
  └── require_review → session 标记 pending_review
         │
         └── 人工决策
                ├── approve → 继续
                └── reject  → session 标记 rejected + 结束
```

---

## 与现有 evolution-policy.yaml 的关系

当前 `evolution-policy.yaml` 控制：
- 哪些 target 可以优化（allow / deny）
- Generator scope 限制

新增的 `state/evolution-policy.yaml` 控制：
- 修改操作自动/审批/禁止

**两者合并**：未来将两个文件合并为一个统一 policy 文件。
**当前**：保持分离，各自独立职责。引用时明确来源。