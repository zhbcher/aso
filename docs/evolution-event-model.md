# Evolution Event Model

> 日期：2026-07-14
> 定义 ASO v2 系统中所有事件类型和事件流。

---

## 设计原则

1. **事件是唯一事实来源** — 所有状态变更通过事件驱动，不直接写状态文件
2. **事件不可变** — 写入后不修改，只追加
3. **事件与 MRX 兼容** — 事件格式与 OpenClaw MRX Event Journal 对齐

---

## 事件存储

```
state/
 └── evolution/
      └── events/
           └── journal.jsonl
```

一行一个 JSON 事件，追加写入。

---

## 事件 Schema

```python
@dataclass
class EvolutionEvent:
    event_id: str                    # evt-{uuid8}
    type: str                        # 见下方事件类型列表
    target: str                      # planner / router / workflow / ...
    session_id: str                  # 关联的 evolution session
    timestamp: str                   # ISO 8601
    payload: dict                    # 事件载荷
    source: str                      # system / user / policy
```

---

## 事件类型

### Skill 生命周期

| 事件类型 | 触发时机 | payload |
|---------|---------|---------|
| `skill.registered` | 新 skill 加入 ASO 管理 | `{skill_path, skill_type, initial_version}` |
| `skill.version_created` | 部署新版本 | `{version, delta_id, parent_version}` |
| `skill.rollback` | 回滚触发 | `{from_version, to_version, reason}` |

### Evolution Session

| 事件类型 | 触发时机 | payload |
|---------|---------|---------|
| `session.started` | session 创建 | `{trigger, trace_count}` |
| `session.step_completed` | pipeline 每步完成 | `{step, status, duration_ms}` |
| `session.failed` | session 异常终止 | `{error, failed_step}` |
| `session.completed` | session 正常结束 | `{verdict, outcome}` |

### Delta 操作

| 事件类型 | 触发时机 | payload |
|---------|---------|---------|
| `delta.generated` | Generator 产出 delta | `{delta_id, operation_count, risk}` |
| `delta.applied` | 部署成功 | `{delta_id, version}` |
| `delta.rejected` | Gate/Sandbox 拒绝 | `{delta_id, reason, gate_result}` |

### 验证

| 事件类型 | 触发时机 | payload |
|---------|---------|---------|
| `validation.passed` | 评估通过 | `{tier, pass_rate, delta}` |
| `validation.failed` | 评估失败 | `{tier, pass_rate, delta, failures}` |
| `validation.regression` | Golden 回归检测 | `{tier, previous_pass_rate, current_pass_rate}` |

### 经验

| 事件类型 | 触发时机 | payload |
|---------|---------|---------|
| `experience.added` | 新增经验记录 | `{entry_id, operation_type, outcome}` |
| `golden.promoted` | trace 升级为 golden | `{trace_id, source_session}` |
| `golden.demoted` | golden 降级 | `{trace_id, reason}` |

---

## 事件使用场景

### Audit

```
events/journal.jsonl

 → 过滤 session_id = "2026-07-14-001"
 → 按时间排序
 → 完整审计追踪
```

### 统计

```
events/journal.jsonl

 → 按 type 分组
 → 统计 session 成功率、delta 通过率、rollback 频率
```

### MRX 集成

```
events/journal.jsonl

 → 按 target 分组
 → feed 进 MRX Event Journal
 → Policy 引擎据此做决策
```

### 恢复

```
events/journal.jsonl

 → 找到最后一个完成的 session
 → 读取 outcome 恢复上下文
```