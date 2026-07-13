---
name: aso
description: >
  Automatic Skill Optimizer: end-to-end skill evolution with data-driven diagnosis,
  TDO-based refactoring, and Delta-gated deployment. Fusion of evolve (trace-based
  lifecycle) and skill-opt (test-driven optimization).
metadata: {"openclaw": {"emoji": "🚀"}}
---

# 🚀 ASO (Automatic Skill Optimizer)

> **全自动技能演化管道**：从生产环境 Trace 到优化验证，结合 evolve 的实时诊断与 skill-opt 的 TDO 重构，实现“感知 → 诊断 → 生成 → 重构 → 量化 → 部署”闭环。

---

## 核心能力

| 能力 | 说明 |
|------|------|
| `aso.run(target, strategy="aso" or "bilevel")` | 完整流水线：观察 → 诊断 → 生成 → 门禁 → 沙箱 → 提案 |
| `trace_to_eval` | 将真实失败 Trace 自动转换为 test cases（补全 evals） |
| `tdo_refactor` | 触发词校准 + 指令精简 + 脚本提取（遵循 agentskills.io 原则） |
| `delta_gate` | 严格量化门禁：Pass Rate 提升 ≥1% 或 Token 降低 ≥5% |
| `safe_deploy` | 基于 manifest 的原子写入 + 自动回滚 |

---

## 工作流（5步闭环）

1. **Observe**: 从 `sessions_history` 或本地 `state/trace_store.json` 采集生产 Trace（默认 100 条）
2. **Diagnose**: 统计瓶颈（工具效率/任务质量/成功率/上下文利用率），生成优先级报告
3. **Generate**:
   - `strategy="bilevel"`: 4 轮 LLM 对话生成候选方案（原始 evolve 行为）
   - `strategy="aso"`: 调用 TDO 优化器 → 触发器校准 → 脚本提取 → 输出极简 SKILL.md
4. **Gate + Sandbox**: 运行 `eval_runner.py`，使用 `delta_calculator.py` 计算 Delta，必须满足：
   - Δ Pass Rate ≥ +1%
   - Δ Token ≤ -5% 或（Δ Token 小幅上升但 Pass Rate 提升 ≥5%）
5. **Report & Deploy**: 生成标准化 Evolution Proposal，人工审批后热更新

---

## 使用示例

```python
# 完整演化（ASO 策略）
from aso.orchestrate import run
result = run(target="planner", strategy="aso")
print(result["success"], result["proposal"]["delta"])

# 仅使用 bilevel 传统策略（兼容 evolve）
result = run(target="workflow", strategy="bilevel")
```

---

## 配置与策略

### evolution-policy.yaml 白名单

```yaml
policy:
  allow:
    - planner
    - workflow
    - prompt
    - skill
  deny:
    - gateway
    - openclaw.json

generator_scopes:
  aso:
    allowed_targets:
      - planner
      - workflow
      - prompt
      - skill
  bilevel:
    allowed_targets:
      - planner
      - workflow
      - prompt
      - memory
      - skill
      - router
```

---

## 目录结构

```
aso/
├── orchestrate.skill      # 编排入口（支持 aso / bilevel）
├── generator/
│   ├── bilevel.py         # 4轮对话生成器（来自 evolve）
│   ├── skill_opt_refactor.py  # TDO 重构器（ASO 策略核心）
│   └── registry.py        # generator 注册表
├── optimizer/             # 来自 skill-opt
│   ├── delta_calculator.py
│   ├── eval_runner.py
│   ├── tdo_calibrator.py
│   ├── snapshot_manager.py
│   └── references/
├── trace_to_eval.py       # 新增：trace 转 evals
├── observe.skill, diagnose.skill, gate.skill, sandbox.skill, ...
├── evals/aso_self_evals.json
├── state/                 # trace_store, manifests, proposals
└── _lib/                  # 共享工具（oc_llm_client, path_utils...）
```

---

## 与 evolve / skill-opt 的区别

| 维度 | ASO | evolve | skill-opt |
| :--- | :--- | :--- | :--- |
| 数据源 | 生产 Trace + 自我测试 | 生产 Trace | 预设 Evals |
| 生成策略 | LLM + TDO 双引擎 | 仅 LLM 4 轮对话 | 仅 TDO 重构 |
| 验证门禁 | Delta 量化（严格） | 沙箱 + 分数门槛 | 手工评估 |
| 自动化程度 | 全自动闭环 | 半自动（ proposal 需人工审批） | 手动触发 |

---

## 注意事项

- **安全边界**: `evolution-policy.yaml` 严禁对 runtime、gateway、scheduler 等核心模块进行自动修改
- **基线管理**: 首次运行会自动初始化 `baseline.json`（需确保有 without_skill / with_skill 数据）
- **回滚保障**: 所有部署写入前生成 manifest 备份，失败自动回滚到上一个稳定版本

---

## 实现状态

- ✅ 目录结构、依赖脚本就绪
- ✅ generator registry 支持 ASO
- ⚠️ gate/sandbox 的 Delta 集成进行中（预计下一个版本完成）
- ⚠️ tdo_calibrator 真实训练逻辑待完善

建议在非生产环境充分验证后再启用 `strategy="aso"`。
