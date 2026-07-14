# ASO v2: 设计冻结文档索引

> 日期：2026-07-14
> 所有设计冻结文档的索引。编码前必须通读。

---

## 核心方案

| 文档 | 内容 |
|------|------|
| `aso-v2-design.md` | 完整架构方案、三个 Phase、15 项工作、优先级 |

## 新增协议文档

| 文档 | 内容 | 原因 |
|------|------|------|
| `evolution-event-model.md` | 事件类型、事件流、与 MRX 集成 | 补全 Phase 0 缺失的事件层 |
| `skill-delta-spec.md` | Delta 数据类型、Operation 类型、TargetPath、RollbackPlan | 冻结 Generator → Gate → Sandbox → Deploy 契约 |
| `evolution-policy.md` | 审批规则、自动/人工/禁止分类、组合规则 | 补全 Phase 0 缺失的 Policy 层 |

## 冻结状态

- `skill-delta-spec.md` — **已冻结**。编码时按此实现，修改需重新评审
- `evolution-event-model.md` — **已冻结**。事件类型可按需扩展，结构不变
- `evolution-policy.md` — **已冻结**。政策规则可配置，Policy Engine 接口不变

## 设计变更记录

| 日期 | 变更 | 文档 |
|------|------|------|
| 2026-07-14 | 初版冻结 | 全部 |
| 2026-07-14 | Phase 3 完成（任务 14, 15, 16） | 无需变更 |

## Phase 完成状态

| Phase | 任务范围 | 状态 | 测试数 |
|-------|---------|------|--------|
| Phase 0 | Foundation (1-6) | ✅ 完成 | 56 |
| Phase 1 | Cognitive Layer (7-9) | ✅ 完成 | 43 |
| Phase 2 | Evaluation System (10-13) | ✅ 完成 | 57 |
| Phase 3 | Memory Integration (14-16) | ✅ 完成 | 64 |
