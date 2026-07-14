# SkillOpt 代码借鉴报告

> 日期：2025-07-14  
> 来源：https://github.com/zhbcher/SkillOpt（克隆至 `/tmp/skillopt` 分析）

---

## 📊 项目结构总览

```
skillopt/
├── config.py                     # 结构化配置（继承、扁平化）
├── optimizer/
│   ├── skill.py                  # 编辑应用与保护区域
│   ├── skill_aware.py            # 技能感知反射（SKILL_DEFECT / EXECUTION_LAPSE）
│   ├── slow_update.py            # 跨夜慢更新（纵向指导）
│   └── ...
├── model/                        # 多后端抽象
├── utils/
│   └── scoring.py                # 分数聚合与多目标奖励
└── types.py

skillopt_sleep/                   # 开箱即用的夜间自进化引擎
├── gate.py                       # 验证门（硬/软/混合）
├── rollout.py                    # 多轮 rollout + 对比反思
├── replay.py                     # 重放与分数聚合
├── dream.py                      # 数据增强 + 关联回忆
├── slow_update.py                # 慢更新（跨 nights）
├── consolidate.py                # 核心循环（reflect → gate → apply）
├── judges.py                     # 规则式评判器（gbrain 兼容）
└── backend.py                    # 后端抽象
```

---

## 🔍 核心模块与 ASO 对应借鉴点

### 1. 训练循环结构（SkillOpt 管道）
```
rollout → reflect → aggregate → select → update → evaluate
```
ASO 已有：`Observe → Diagnose → Generate → Sandbox + Gate → Report & Deploy`  
**借鉴**：
- 将 `reflect` 细分 failures/successes；限制 `edit_budget`（生成编辑数量上限）
- 增加独立 held‑out 验证集（gate 时使用），避免过拟合当前测试集

---

### 2. 编辑保护机制（skill.py）
- 保护区标记：
  ```
  <!-- SLOW_UPDATE_START --> ... <!-- SLOW_UPDATE_END -->
  <!-- APPENDIX_START --> ... <!-- APPENDIX_END -->
  ```
- 行为：step‑level edits 禁止修改保护区；`append`/`insert_after` 自动插入到最早保护区之前，确保保护区始终在文档尾部。
- **ASO 可借鉴**：
  - 在 `apply_edits` 中检查 `target` 是否落在保护区，是则跳过或重定位
  - 引入 `_is_in_protected_region(skill, target)` 辅助

---

### 3. 技能感知反射（skill_aware.py）
Failure reflections 分为：
- **SKILL_DEFECT**：技能本身错误/不足 → 生成 body edit
- **EXECUTION_LAPSE**：技能已有正确规则但执行失败 → 仅生成 `appendix_notes`（不修改主体）
Success reflections 可标注 `DISCOVERY` / `OPTIMIZATION`（统计用）
- **ASO 可借鉴**：
  - 在 `generator` 或 `orchestrate` 中集成该分类逻辑，保护有效规则不被删除
  - 为 skill 增加 `appendix` 区域（`APPENDIX_START/END`），存放 execution‑lapse 提醒

---

### 4. 验证门与多目标评分（gate.py, scoring.py）
- `select_gate_score(hard, soft, metric="mixed", mixed_weight=0.5)` → 单一比较分数
- `evaluate_gate(...)` 返回 `accept_new_best` / `accept` / `reject`
- 多目标奖励：`multi_objective_reward(pairs, w_acc, w_tokens, w_latency, ...)` 综合正确率与成本
- **ASO 可借鉴**：
  - 将 `sandbox` 的 `verdict` 替换为 `evaluate_gate`，支持 “hard/soft/mixed” 可配置
  - 权重（权重、Token 参考、延迟参考）纳入 candidate 评估

---

### 5. 规则式评判器（judges.py）
纯本地、无 LLM 调用：
- `section_present(name)`：Markdown 标题存在
- `regex(pattern)`：正则匹配
- `max/min_chars(n)`：长度限制
- `contains(text)`：子串包含
- `tool_called(name)`：工具被调用（可近似）
- 返回 `(hard, soft, rationale)`，所有检查通过 → hard=1.0
- **ASO 可借鉴**：
  - 在 `_lib/judge.py` 增加 rule‑judge 实现（与 LLM‑as‑a‑Judge 并存），降低成本

---

### 6. 多轮 rollout 与对比反思（rollout.py）
- `multi_rollout(task, k=3, workers=...)`：同一任务多次执行，获取 good vs bad 对比
- `contrastive_reflect(...)`：选择 spread 最大的任务，提取对比样本，生成规则
- **ASO 可借鉴**：
  - `eval_runner` 每个 test case 运行 `k` 次（可并行），收集分布
  - `reflect` 改为对比式，提高编辑质量

---

### 7. 经验回放 + Dream 增强（dream.py）
- `dream_augment(real_tasks, factor)`：模板改写生成合成训练样本（`split="train"`）
- `recall_similar(new_tasks, history, k)`：Jaccard 相似度检索历史相关任务加入训练
- **ASO 可借鉴**：
  - 失败 trace 聚类/改写后加入 `evals/train`，提升多样性
  - 存储历史任务到 `state/task_history.json`，每晚选取 `top‑k` 加入训练集

---

### 8. 慢更新 / 跨夜记忆（slow_update.py）
- 跨 night 比较 `prev_pairs` vs `curr_pairs`，生成纵向指导块
- 写入 `SLOW_UPDATE_START/END` 保护区，step edits 永不触碰
- **ASO 可借鉴**：
  - 部署后保存 `(skill, replay_pairs)` 为前一晚基线
  - 每晚执行 `run_slow_update` 生成指导块并写入 skill

---

### 9. 配置与后端抽象
- `config.py`：支持 `_base_` 继承、结构化 sections、flat 映射
- `backend.py`：统一接口（chat/exec/attempt/attempt_with_tools/judge）
- **ASO 可借鉴**：
  - `config.yaml` 升级为结构化（`model`、`train`、`optimizer`、`evaluation`、`env`）
  - `oc_llm_client` 实现 `Backend` 接口，便于切换提供商

---

### 10. 工程化亮点
- 类型安全（dataclasses）
- 并发（ThreadPoolExecutor + `SKILLOPT_SLEEP_WORKERS`）
- 观测性（holdout_detail、reflect_raw、call_error）

---

## ✅ ASO 优化路线图（优先级）

| 优先级 | 模块 | 借鉴点 | 预计工作量 |
|--------|------|--------|-----------|
| P0 | `apply_edits` / `tdo_calibrator` | 编辑保护（禁止改保护区） | 1–2 天 |
| P0 | `sandbox.skill` | held‑out gate（混合分数 + 严格提升） | 2–3 天 |
| P1 | `generator` | 技能感知反射（SKILL_DEFECT vs EXECUTION_LAPSE） | 3–4 天 |
| P1 | `_lib/judge.py` | 集成 rule‑judge（减少 LLM 依赖） | 2 天 |
| P2 | `trace_to_eval` → dream/recall | 任务增强与历史检索 | 1 周 |
| P2 | `gate` → multi‑objective reward | 引入 Token/延迟权重 | 2–3 天 |
| P3 | `config.yaml` → structured config | `_base_` 与 flat map | 3 天 |
| P3 | `oc_llm_client` → Backend | 厂商抽象 | 1 周 |

---

## 📌 下一步建议（P0 + P1 实操）

1. **编辑保护**
   - 在 `optimizer/tdo_calibrator.py` 或 `sandbox._apply_edits` 时，添加 `_is_in_protected_region` 检查，屏蔽对保护区（slow‑update 与 appendix）的修改
   - 可选：若 edit 目标在保护区内，转为 `append` 到最早保护区之前

2. **Held‑out Gate（混合分数）**
   - 在 `sandbox.skill` 中创建 `evals/held_out/`（从现有 golden 拆分或新增）
   - 引入 `select_gate_score`（支持 mixed metric）与 `evaluate_gate` 决策
   - 记录 `holdout_baseline/holdout_candidate` 与 `gate_action`

3. **技能感知反射**
   - 修改 `generator` 或 `orchestrate`：生成 edit 时附加 `reflection_type` 与 `appendix_notes`
   - 为 skill 增加 `APPENDIX_START/END` 区域，consolidate 时处理 notes

4. **Rule‑Judge**
   - 扩展 `_lib/judge.py` 添加 `rule_judge(checks, response, tools_called)`，复用 SkillOpt 的 `judges.py` 逻辑
   - `eval_runner` 优先使用 rule‑judge（成本更低）

---

> 完整实现细节可在后续迭代中逐步落地。此文档作为“SkillOpt 借鉴方案”存档，便于追溯与讨论。
