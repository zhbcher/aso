# Skill Delta Spec

> 日期：2026-07-14
> 冻结 SkillDelta 数据类型，作为 Generator → Gate → Sandbox → Deploy 的契约。

---

## 核心思想

不替换整个文件，只描述增量变更。类似 Git patch，但结构化且可验证。

---

## 顶层结构

```python
@dataclass
class SkillDelta:
    delta_id: str                       # delta-{uuid8}
    session_id: str                     # 所属 evolution session
    target: str                         # planner / router / workflow / ...
    base_version: str                   # v3（修改前版本号）

    operations: list[DeltaOperation]    # 变更操作列表

    risk: str                           # low / medium / high
    generation_confidence: float        # 0.0 - 1.0（来自 Generator）
    expected_effect: str                # "reduce multi-turn failure rate by 30%"
    change_rationale: str               # 为什么这么改（关联 Reflect 结果）

    rollback_plan: RollbackPlan         # 如何回滚
```

---

## DeltaOperation

```python
@dataclass
class DeltaOperation:
    """单次增量操作。"""
    type: str                            # 见下方操作类型列表
    target: TargetPath                   # 修改目标路径
    before: str | None                   # 原文（modify/remove 时必填）
    after: str | None                    # 新内容（add/modify 时必填）
    reason: str                          # 为什么改（人可读，>= 10 字符）
```

### 操作类型

| type | 含义 | before | after |
|------|------|--------|-------|
| `instruction_add` | 增加指令 | null | 新指令内容 |
| `instruction_remove` | 删除指令 | 原文 | null |
| `instruction_modify` | 修改指令 | 原文 | 新内容 |
| `constraint_add` | 增加约束 | null | 新约束 |
| `constraint_remove` | 删除约束 | 原文 | null |
| `constraint_modify` | 修改约束 | 原文 | 新内容 |
| `step_add` | 增加 workflow 步骤 | null | 新步骤定义 |
| `step_remove` | 删除 workflow 步骤 | 原文 | null |
| `step_modify` | 修改 workflow 步骤 | 原文 | 新内容 |
| `workflow_reorder` | 调整步骤顺序 | 原顺序 | 新顺序 |
| `tool_call_add` | 增加工具调用 | null | 工具调用定义 |
| `tool_call_remove` | 删除工具调用 | 原文 | null |
| `tool_call_modify` | 修改工具调用参数 | 原文 | 新内容 |

---

## TargetPath

支持结构化定位，不限于文本行号。

```python
@dataclass
class TargetPath:
    """修改目标路径——适配多种 Skill 格式。"""
    file: str                            # planner.skill / config.yaml
    selector_type: str                   # yaml_path / workflow_node / text_section / line_range
    selector: str                        # 具体选择器

    # 例子：
    # {"file": "planner.skill",           "selector_type": "text_section",  "selector": "workflow.step3"}
    # {"file": "planner.skill",           "selector_type": "line_range",   "selector": "45-52"}
    # {"file": "config.yaml",             "selector_type": "yaml_path",    "selector": "policy.max_retries"}
    # {"file": "planner.skill",           "selector_type": "workflow_node","selector": "steps[3].verification"}
```

---

## RollbackPlan

```python
@dataclass
class RollbackPlan:
    """每个 Delta 自带回滚方案。"""
    type: str                            # version_restore / reverse_delta / manual
    target_version: str | None           # version_restore 时指定
    reverse_operations: list[DeltaOperation] | None  # reverse_delta 时指定
    notes: str                           # 回滚注意事项
```

---

## 完整例子

```json
{
  "delta_id": "delta-001",
  "session_id": "2026-07-14-001",
  "target": "planner",
  "base_version": "v3",

  "operations": [
    {
      "type": "instruction_modify",
      "target": {
        "file": "planner.skill",
        "selector_type": "text_section",
        "selector": "workflow.step3"
      },
      "before": "Execute the tool call immediately",
      "after": "Before executing, verify the input parameters are valid",
      "reason": "15% of multi-turn failures caused by missing parameter validation"
    },
    {
      "type": "constraint_add",
      "target": {
        "file": "planner.skill",
        "selector_type": "text_section",
        "selector": "constraints"
      },
      "before": null,
      "after": "After turn 8, force context compression",
      "reason": "Context window overflow in long conversations"
    }
  ],

  "risk": "low",
  "generation_confidence": 0.85,
  "expected_effect": "reduce multi-turn failure rate by 30-50%",
  "change_rationale": "Reflect identified SKILL_DEFECT: planner lacks verification and compression steps",

  "rollback_plan": {
    "type": "reverse_delta",
    "target_version": null,
    "reverse_operations": [
      {
        "type": "instruction_modify",
        "target": {"file": "planner.skill", "selector_type": "text_section", "selector": "workflow.step3"},
        "before": "Before executing, verify the input parameters are valid",
        "after": "Execute the tool call immediately",
        "reason": "Rollback: restore original step3"
      },
      {
        "type": "constraint_remove",
        "target": {"file": "planner.skill", "selector_type": "text_section", "selector": "constraints"},
        "before": "After turn 8, force context compression",
        "after": null,
        "reason": "Rollback: remove added constraint"
      }
    ],
    "notes": "Simple reverse delta, no state migration needed"
  }
}
```

---

## 验证规则

| 规则 | 条件 |
|------|------|
| operation_count | ≤ 5 条 |
| total_changed_lines | ≤ 50 行 |
| reason 长度 | ≥ 10 字符 |
| risk 一致性 | 3+ 条 operation 不能标 low |
| before/after 一致性 | add 类 before=null, remove 类 after=null |
| target 范围 | 必须在 evolution-policy.yaml 允许范围内 |
| rollback_plan | 非 null |