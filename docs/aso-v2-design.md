# ASO v2: Skill Evolution Infrastructure

> 日期：2026-07-14
> 基于与 GPT 三轮对话融合的完整设计方案
> 吸收 SkillOpt 核心思想 + OpenClaw 生产安全体系

---

## 定位升级

```
v1: Skill Optimizer         →    v2: Skill Evolution Infrastructure
     ─────────────                 ──────────────────────────────
     自动优化脚本                      技能进化基础设施
     一次性修改                         持久化进化状态
     统计诊断                           认知层反射
     文件级替换                         增量 Delta Patch
     无状态                             有状态 + 经验复用
```

ASO v2 不是 SkillOpt 的 OpenClaw 移植版，而是 **把 SkillOpt 的 Evolution Loop 吸收到 OpenClaw 生产安全体系内**。

---

## 架构总览

```
               OpenClaw Runtime
                     │
                     ▼
              Trace Collector         ─── observe.skill
                     │
                     ▼
           Evolution Experience Store  ─── state/evolution/ (NEW)
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
    Diagnose       Reflect      Experience
   (Metrics)    (Cognitive)    (Memory)
        │            │            │
        └────────────┼────────────┘
                     ▼
            Evolution Planner     ─── NEW: evolution_planner.py
                     │
                     ▼
             Skill Delta Model   ─── NEW: SkillDelta (增量 Patch)
                     │
                     ▼
           Validation Engine
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
     Recent       Golden       Failures
     Tier         Tier          Tier
        │            │            │
        └────────────┼────────────┘
                     ▼
             Sandbox + Gate       ─── 现有 gate.skill + sandbox.skill (升级)
                     │
                     ▼
            Deploy / Rollback     ─── 现有 deploy.skill + rollback.skill
                     │
                     ▼
          Evolution Memory Update ─── NEW: 更新 optimization_memory
```

---

## Phase 0: Evolution Foundation（必须先做）

### 0.1 Evolution Session

替代当前无状态的一次性运行。

```
state/
 └── evolution/
      ├── index.json
      └── sessions/
           └── 2026-07-14-001/
                ├── manifest.json
                ├── observation.json
                ├── diagnosis.json
                ├── reflection.json      (NEW)
                ├── proposal.json
                ├── validation.json
                ├── deployment.json
                └── outcome.json
```

**index.json** — 所有 session 的索引

```json
{
  "sessions": [
    {
      "id": "2026-07-14-001",
      "target": "planner",
      "status": "deployed",
      "created_at": "2026-07-14T10:00:00Z",
      "delta_id": "delta-001",
      "outcome_summary": "pass_rate +8%, tokens -12%"
    }
  ],
  "latest_by_target": {
    "planner": "2026-07-14-001",
    "router": "2026-07-13-003"
  }
}
```

**manifest.json** — 每个 session 的元数据

```json
{
  "session_id": "2026-07-14-001",
  "target": "planner",
  "trigger": "manual",
  "trace_count": 100,
  "timeline": [
    {"step": "observe",    "started_at": "...", "completed_at": "...", "status": "ok"},
    {"step": "diagnose",   "started_at": "...", "completed_at": "...", "status": "ok"},
    {"step": "reflect",    "started_at": "...", "completed_at": "...", "status": "ok"},
    {"step": "generate",   "started_at": "...", "completed_at": "...", "status": "ok"},
    {"step": "validate",   "started_at": "...", "completed_at": "...", "status": "ok"},
    {"step": "gate",       "started_at": "...", "completed_at": "...", "status": "passed"},
    {"step": "sandbox",    "started_at": "...", "completed_at": "...", "status": "ok"},
    {"step": "deploy",     "started_at": "...", "completed_at": "...", "status": "deployed"}
  ],
  "outcome": {
    "verdict": "deployed",
    "delta_pass_rate": 0.08,
    "delta_tokens": -0.12,
    "rolled_back": false
  }
}
```

**修改点：**
- 新建 `state/evolution/` 目录结构
- `orchestrate.skill` 增加 session 创建和管理
- `path_utils.py` 增加 EVOLUTION_SESSION_DIR 常量

---

### 0.2 Skill Delta Model

核心变更：Generator 不再输出 `modify_skill_file` 整文件替换，而是输出 **增量 Patch**。

**SkillDelta 数据结构**

```python
@dataclass
class SkillDelta:
    """增量技能修改——不是替换整个文件，而是精确描述变更。"""
    delta_id: str                            # delta-001
    session_id: str                          # 所属 session
    target: str                              # planner / router / workflow
    base_version: str                        # v3（修改前版本号）

    operations: list[DeltaOperation]         # 变更操作列表

    risk: str                                # low / medium / high
    expected_effect: str                     # "improve pass rate for multi-turn tasks"
    change_rationale: str                    # 为什么这么改（关联 Reflect 结果）

@dataclass
class DeltaOperation:
    """单次增量操作。"""
    type: str                                # add_instruction / remove_instruction /
                                             # modify_instruction / add_tool_call /
                                             # modify_workflow / add_step / remove_step /
                                             # modify_constraint
    location: str                            # workflow.step3 / prompt.tone / ...
    before: str | None                       # 原文（modify/remove 时必填）
    after: str | None                        # 新内容（add/modify 时必填）
    reason: str                              # 为什么改（人可读）
```

**例子：**

```json
{
  "delta_id": "delta-001",
  "session_id": "2026-07-14-001",
  "target": "planner",
  "base_version": "v3",
  "operations": [
    {
      "type": "modify_instruction",
      "location": "planner.workflow.step3",
      "before": "Execute the tool call immediately",
      "after": "Before executing, verify the input parameters are valid",
      "reason": "Missing verification step caused 15% of multi-turn failures"
    },
    {
      "type": "add_constraint",
      "location": "planner.constraints",
      "before": null,
      "after": "After turn 8, force context compression",
      "reason": "Context window overflow after long conversations"
    }
  ],
  "risk": "low",
  "expected_effect": "reduce multi-turn failure rate by 30-50%",
  "change_rationale": "Reflect identified SKILL_DEFECT: planner lacks verification and compression steps"
}
```

**修改点：**
- 新增 `_lib/delta.py` — SkillDelta / DeltaOperation 定义 + 序列化 + apply 逻辑
- 修改 `generator/` 输出改为 SkillDelta
- 修改 `gate.skill` — 不再只检查文件语法，增加增量合理性检查
- 修改 `sandbox.skill` — apply delta 而非替换整个文件
- 修改 `report.skill` — 输出包含 delta 信息
- 修改 `deploy.skill` — 部署 delta 而非整文件

---

### 0.3 Skill Version Tracking

当前 `state/manifests.json` 只有 3 个字段，没有版本概念。

**SkillVersion 记录**

```json
{
  "planner": {
    "current_version": "v3",
    "versions": [
      {"version": "v1", "delta": null, "deployed_at": "2026-07-01"},
      {"version": "v2", "delta": "delta-001", "deployed_at": "2026-07-08"},
      {"version": "v3", "delta": "delta-002", "deployed_at": "2026-07-14"}
    ],
    "rollback_target": "v2"
  }
}
```

**修改点：**
- 升级 `state/manifests.json` schema
- `deploy.skill` 部署成功后更新 version
- `rollback.skill` 回滚时更新 version

---

### 0.4 Optimization Memory Schema

**只定义结构，不实现引擎。**

```json
// state/optimization_memory.json
{
  "entries": [],
  "schema_version": "v1"
}
```

每条记录：

```json
{
  "entry_id": "om-001",
  "session_id": "2026-07-14-001",
  "operation_type": "add_constraint",
  "target": "planner",
  "context": {
    "failure_pattern": "multi-turn context overflow",
    "root_cause": "missing compression step"
  },
  "delta_summary": "add verification + compression",
  "outcome": {
    "pass_rate_delta": 0.08,
    "tokens_delta": -0.12,
    "deployed": true,
    "rolled_back": false
  },
  "confidence": 0.7
}
```

与 QMD Memory 的关系：
- Optimization Memory 是 **结构化** 的优化经验
- QMD Memory 是 **语义化** 的知识检索
- 两者互补：Optimization Memory 的数据可以 feed 进 QMD 做语义检索

**修改点：**
- 新建 `state/optimization_memory.json`
- `report.skill` 每次部署后写入一条记录
- `path_utils.py` 增加 OPTIMIZATION_MEMORY_FILE 常量

---

## Phase 1: Cognitive Layer

### 1.1 Reflect Engine

当前 ASO 缺失的关键层。在 Diagnose（统计）和 Generate（修改）之间增加认知推理。

**新文件：`reflect.skill`**

```
职责：
  接收 Diagnose 的统计报告
  输出根因分析和 failure 分类

输入：
  - diagnose 报告（MetricsReport）
  - 原始 trace 数据

输出：
  - ReflectionResult

不做：
  不生成修改方案（那是 Generate 的事）
  不输出代码
```

**ReflectionResult 结构**

```python
@dataclass
class ReflectionResult:
    failure_type: str            # SKILL_DEFECT / EXECUTION_LAPSE / ENVIRONMENT_ISSUE / UNCLEAR
    root_cause: str              # "planner lacks context compression after turn 8"
    evidence: list[str]          # 支撑根因的具体 trace 证据
    failure_examples: list[dict] # 典型失败案例（< 3 个，避免 token 膨胀）
    recommended_change_type: str # instruction_add / workflow_modify / constraint_add / ...
    confidence: float            # 0.0 - 1.0
```

**failure_type 分类（来自 SkillOpt skill_aware.py）：**

| 类型 | 含义 | 处理方式 |
|------|------|---------|
| SKILL_DEFECT | 技能本身缺少规则/流程 | 修改 skill 主体 |
| EXECUTION_LAPSE | 技能规则正确，执行时没遵守 | 加 appendix 提醒，不改主体 |
| ENVIRONMENT_ISSUE | 外部原因（API 挂了、网络问题） | 不修改 skill，记录到 memory |
| UNCLEAR | 不确定 | 标记 low confidence，需要人工 |

**修改点：**
- 新增 `reflect.skill`
- 修改 `orchestrate.skill` — 在 diagnose 后调用 reflect
- 修改 pipeline 流程：Observe → Diagnose → **Reflect** → Generate → Validate

---

### 1.2 Diagnose 升级

当前 diagnose 只有统计评分，需要增加趋势感知。

**保持现有 4 个维度评分不变，增加：**
- 时间窗口对比（最近 vs 历史）
- 失败模式聚类（相同的失败原因出现频率）
- 跨 session 趋势

**不破坏现有接口，向后兼容。**

---

## Phase 2: Evaluation System

### 2.1 Experience Tier（替换 ML train/val/test split）

OpenClaw 不是 ML 训练，不需要随机拆分。使用软件测试分层：

| Tier | 内容 | 来源 | 用途 |
|------|------|------|------|
| **Recent** | 最近 100 条 trace | 本次 Observe 采集 | 主评估：候选 delta 是否有效 |
| **Golden** | 人工确认的优质任务 | 逐步积累 | 回归保护：不能破坏已确认场景 |
| **Failures** | 历史失败 trace | session 自动存档 | 针对性修复：确保不再犯 |
| **Historical** | 归档 trace | 自动归档的旧 trace | 长期回归（非必须） |

**Golden Trace 数据结构**

```json
{
  "golden_id": "golden-001",
  "task_id": "task-xxx",
  "target": "planner",
  "description": "多轮对话总结",
  "expected_outcome": {
    "success": true,
    "max_tokens": 5000,
    "max_steps": 10
  },
  "added_by": "session-2026-07-01-002",
  "added_at": "2026-07-01T10:00:00Z",
  "tags": ["multi-turn", "summarization"]
}
```

**修改点：**
- 新建 `evals/golden/` 和 `evals/failures/` 目录
- 修改 `benchmark.skill` — 支持按 tier 分组评估
- 修改 `sandbox.skill` — 评估时跑全部 tier
- `gate.skill` 增加 tier 级门禁：Golden 必须无回归

---

### 2.2 Gate 升级：Delta 合理性检查

当前 gate 做：
- 结构检查
- scope lock
- 语法检查
- risk 检查

**新增检查：**

| 检查 | 内容 | 通过条件 |
|------|------|---------|
| delta_scope | 修改范围不超出 target | operation.location 必须在 target skill 内 |
| delta_reason | 每条 operation 必须有 reason | reason 非空且 >= 10 字符 |
| delta_risk_consistency | risk 声明与 operations 数量匹配 | 3+ 个 operation 不能标 low risk |
| change_budget | 单次修改量限制 | max 5 operations / max 50 lines changed |
| golden_regression | Golden tier 无退化 | Golden pass rate 100% |

---

## Phase 3: Learning Layer

### 3.1 Experience Replay（Phase 3 实现）

依赖 Phase 0 的 Evolution State 和 Optimization Memory 积累足够数据后再启用。

**实现时机：**
- Optimization Memory 中至少有 20 条有效记录
- 或者 ASO 运行超过 30 天

**核心逻辑：**
1. 收到新优化请求
2. 检索 Optimization Memory 中相似场景
3. 如果有成功先例，优先复用
4. 如果之前有失败尝试，避免重复

---

### 3.2 Meta Optimization Memory（Phase 3 启用）

统计各种优化操作的成功率：

| 操作类型 | 尝试次数 | 成功次数 | 成功率 |
|---------|---------|---------|-------|
| add_constraint | 8 | 7 | 87.5% |
| add_instruction | 5 | 4 | 80.0% |
| remove_instruction | 3 | 1 | 33.3% |
| modify_workflow | 4 | 3 | 75.0% |

Generator 可以根据这些统计选择高成功率的策略。

---

## 文件变更清单

### 新增文件

| 文件 | 作用 |
|------|------|
| `_lib/delta.py` | SkillDelta / DeltaOperation 数据类型 + apply 逻辑 |
| `reflect.skill` | Reflect Engine 认知层 |
| `state/evolution/index.json` | Session 索引 |
| `state/optimization_memory.json` | 优化记忆骨架 |
| `docs/aso-v2-design.md` | 本文档 |

### 修改文件

| 文件 | 修改内容 |
|------|---------|
| `_lib/path_utils.py` | 新增 EVOLUTION_SESSION_DIR / OPTIMIZATION_MEMORY_FILE 常量 |
| `_lib/types.py` | 新增 ReflectionResult / SkillDelta / SkillVersion 类型 |
| `orchestrate.skill` | Session 管理 + Reflect 集成 + 持久化 |
| `diagnose.skill` | 增加趋势感知 + 失败模式聚类 |
| `gate.skill` | 增加 delta 合理性检查 + tier 门禁 + change budget |
| `generator/` | 输出改为 SkillDelta（增量而非全量） |
| `sandbox.skill` | 支持 apply delta + tier 分层评估 |
| `benchmark.skill` | 支持 tier 分组评估 |
| `report.skill` | 输出包含 delta + reflection 信息 |
| `deploy.skill` | 部署 delta + 更新 version |
| `rollback.skill` | 回滚时更新 version |
| `state/manifests.json` | 升级 schema，增加 version 跟踪 |

### 目录变更

```
state/
 ├── evolution/                  (NEW)
 │    ├── index.json
 │    └── sessions/
 │         └── YYYY-MM-DD-NNN/
 ├── optimization_memory.json    (NEW)
 ├── manifests.json              (UPGRADE)
 └── trace_store.json

evals/
 ├── golden/                     (NEW)
 ├── failures/                   (NEW)
 └── aso_self_evals.json
```

---

## 优先级和执行顺序

### 阶段 0: Foundation（P0，当前启动）

```
Week 1-2:

1. Evolution Session 目录结构 + index.json
2. SkillDelta 数据类型 + apply 逻辑
3. Skill Version 追踪
4. Optimization Memory schema（只定义结构）
5. path_utils.py 升级
```

### 阶段 1: Cognitive（P0，Week 3-4）

```
6. Reflect Engine（reflect.skill）
7. Diagnose 升级（趋势 + 聚类）
8. Pipeline 集成 Reflect
```

### 阶段 2: Evaluation（P1，Week 5-6）

```
9. Experience Tier（Recent / Golden / Failures / Historical）
10. Gate 升级（delta 检查 + tier 门禁 + change budget）
11. Generator 输出改为 SkillDelta
12. Sandbox 升级（apply delta + tier 评估）
```

### 阶段 3: Learning（P2，条件触发）

```
13. Experience Replay Engine
14. Meta Optimization Memory 启用
15. Generator 策略感知
```

---

## 不做的

| 特性 | 理由 |
|------|------|
| Skill Version Graph（Git 分支） | 当前触发频率不需要，change history 足够 |
| 自动无限进化循环 | 危险，必须保留人工审批 |
| 固定 Benchmark 训练模式 | SkillOpt 的研究方法，不适用于 OpenClaw 无限任务场景 |
| ML train/test split | 生产系统不需要，Experience Tier 更合适 |

---

## 与现有系统的关系

| 系统 | 关系 |
|------|------|
| QMD Memory | Optimization Memory 的语义检索后端 |
| MRX | 共享 Evolution State 基础设施 |
| Task Kernel | ASO 优化的下游消费者 |
| Evolution Package | 两个方向正在汇合，未来合并为 Evolution Layer |