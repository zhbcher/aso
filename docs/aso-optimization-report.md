# ASO 优化审计报告

**审计时间**: 2026-07-13  
**审计范围**: `/Users/zhoubo/.openclaw/workspace/.agents/skills/aso/`  
**审计框架**: skill-opt 六维度模型  
**基础版本**: post `trigger-opt` / `trace_to_eval` 演化版

---

## 1. 优化摘要

| 严重等级 | 数量 | 说明 |
|---------|------|------|
| HIGH | 4 | 阻断运行或产生安全隐患，必须立即修复 |
| MEDIUM | 6 | 体验/可维护性问题，影响较大但不会直接崩溃 |
| LOW | 4 | 规范/文档层面，建议优化 |

**整体健康度**: 🟡 中等（有几个会阻止 pipeline 正常完成的高严重问题）

---

## 2. 详细诊断

### 2.1 Description / 触发器边界

#### Issue #1 [HIGH] - SKILL.md 描述与代码支持能力不匹配
- **位置**: `SKILL.md` > description + "5 步工作流" 说明
- **问题**: SKILL.md 描述说 default strategy 是 `aso`，但 `orchestrate.skill` 中 `DEFAULT_BUDGET` 和 `run()` 签名里 `strategy="bilevel"`。这里的默认值不一致会让用户困惑。
- **影响**: 用户调 `run(target="x")` 不传 strategy，实际走的是 bilevel，而非文档说的 aso。文档中的"默认 TDO 重构"并未生效。
- **修复建议**:
  1. 统一 `orchestrate.skill` 的 `run()` 默认值为 `strategy="aso"`，或在 SKILL.md 中明确说明"默认其实是 bilevel，建议显式传 aso"。
  2. 在 SKILL.md 的入口代码块中加注释标明推荐策略。
- **预期收益**: 消除文档/代码不一致导致的迷惑，让"直接跑 ASO"的承诺可兑现。
- **优先级**: P0

#### Issue #2 [HIGH] - 触发语句过于宽泛，可能误触发
- **位置**: `SKILL.md` > "触发" 段落
- **问题**: "当老板要求'优化技能''诊断技能''自动演化 skill'...时，直接走本 skill"。这些短语非常常见，在普通对话中也可能出现，可能导致不必要的 pipeline 启动。
- **影响**: 误触发消耗大量 token（默认 50000），甚至可能误修改技能文件。缺少"上下文证据"要求（如出现 trace、日志、明确技能名）。
- **修复建议**: 收紧触发器描述，要求至少一个强信号才触发：
  - 明确提到技能文件路径
  - 或提到 trace / benchmark / delta
  - 或用户显式说"跑 ASO/evolve/skill-opt 流程"
- **预期收益**: 减少误触发率，保护 token 预算。
- **优先级**: P0

#### Issue #3 [MEDIUM] - 缺少"不适合触发"的说明
- **位置**: `SKILL.md` 整体
- **问题**: 没有说明什么时候不该触发 ASO（比如：单次普通对话、没有 trace 数据时、用户只是讨论概念）。
- **影响**: agent 和用户都可能误用。
- **修复建议**: 在 SKILL.md 中加"NOT 触发条件"章节。
- **优先级**: P2

### 2.2 上下文 & 冗余

#### Issue #4 [MEDIUM] - 安全边界在 SKILL.md 和 deploy.skill 中有重复
- **位置**: `SKILL.md` > "安全边界" vs `deploy.skill` > `_validate_proposal` 等
- **问题**: SKILL.md 里用中文段落列出了"禁止自动修改"的目标，`deploy.skill` 里通过 `evolution-policy.yaml` 实现 deny 逻辑，`gate.skill` 里也有 `_check_scope_lock` 重复检查。三个地方维护同一份列表，容易漂移。
- **影响**: 若某次修改只更新了 SKILL.md 而忘了更新 yaml，实际允许的 target 与文档声称的不一致。
- **修复建议**:
  1. 明确 SKILL.md 中的安全列表是"文档引用"，实际以 `evolution-policy.yaml` 为准。
  2. 在 SKILL.md 里加一句"实际 enforced 位置见 evolution-policy.yaml"。
- **预期收益**: 减少维护负担，消除文档/实现不一致。
- **优先级**: P1

#### Issue #5 [MEDIUM] - 硬门禁描述与 sandbox 实际实现不一致
- **位置**: `SKILL.md` > "硬门禁" vs `sandbox.skill` > `_calc_delta`
- **问题**: SKILL.md 说硬门禁有三个维度（ΔPassRate≥+1%, ΔToken≤-5%, 或 ΔPassRate≥+5% 时允许小幅 token 上升），但 `sandbox.skill` 中 `delta_calculator.py` 的具体规则未见公开，而 `sandbox.skill` 里也未实现对这三个规则的硬拒绝逻辑——它只计算 delta 和 verdict，最终判断似乎交给 deploy。
- **影响**: 文档承诺的"不满足则直接拒绝，不进入 deploy"在实现中可能是软门禁，甚至只在 report 阶段隐式处理。这给绕过门禁提供了可能。
- **修复建议**:
  1. 在 `sandbox.skill` 里加入明确的 delta gate 判断，当 delta 不满足硬门禁条件时返回 `verdict="rejected"` + reason。
  2. 在 `orchestrate.skill` 的 `run()` 中增加对 sandbox_result.verdict 的硬检查， verdict 为 "rejected" 时直接终止，不进入 report/deploy。
- **预期收益**: 硬门禁真正硬起来，防止劣质 candidate 进入部署流程。
- **优先级**: P0

### 2.3 脚本 CLI 契约

#### Issue #6 [HIGH] - 脚本入口契约不统一
- **位置**: `trace_to_eval.py`, `optimizer/eval_runner.py`, `optimizer/delta_calculator.py`
- **问题**: 
  - `trace_to_eval.py` 暴露了 CLI 但不知道它和 `eval_runner.py` 的输入输出契约是否一致。
  - `optimizer/` 下的多个子模块各自处理参数，没有统一的入口说明。
- **影响**: 维护者/agent 很难知道"如果要手动跑 eval，该调哪个脚本"。
- **修复建议**:
  1. 在 `scripts/` 或根目录加一个 `README.cli.md`，列出每个脚本的用法、输入格式、输出路径。
  2. 统一使用 `argparse` 或 `click`，保持 `--skill-path`、`--evals`、`--output` 三参数契约一致（目前 `eval_runner.py` 已经有，但 `trace_to_eval.py` 的参数格式未在文档中标准化）。
- **优先级**: P1

#### Issue #7 [LOW] - sandbox.skill 中的 `_load_benchmark` 与 `_load_benchmark_from` 签名重复
- **位置**: `sandbox.skill`
- **问题**: 两个方法几乎一样的逻辑，一个从 EVOLVE_DIR 加载，一个从 work_dir 加载。可以合并为一个带路径参数的函数。
- **修复建议**: 合并为 `_load_benchmark(work_dir=EVOLVE_DIR)` 一个函数。
- **优先级**: P2

### 2.4 测试覆盖

#### Issue #8 [HIGH] - 测试目录结构与 aso_self_evals.json 不匹配
- **位置**: `tests/`, `evals/`
- **问题**: 
  - `tests/` 里只有 `test_delta_calculator.py` 和 `test_integration.py`。
  - `evals/` 目录有 `aso_self_evals.json`，但未验证该文件是否存在、格式是否正确。
  - 没有 unit test 覆盖 `gate.skill`、`diagnose.skill`、`observe.skill` 的核心逻辑。
  - `trace_to_eval.py` 作为新增工具，也没有对应测试。
- **影响**: 重构时代码质量无法快速确认，容易的 regression bug 没被发现。
- **修复建议**:
  1. 为 `gate.skill`（5 个 check）、`diagnose.skill`（4 个评分维度）、`observe.skill` 各加单元测试。
  2. 加一个 `test_trace_to_eval.py` 校验 `trace_to_eval.py` 的输出格式兼容 `eval_runner.py`。
  3. 加一个 pre-run 检查，启动 pipeline 前验证 `evals/aso_self_evals.json` 存在且符合 schema。
- **优先级**: P1

#### Issue #9 [MEDIUM] - test_integration.py 可能是端到端测试，执行成本高
- **位置**: `tests/test_integration.py`
- **问题**: 从文件名推测是集成测试，但无断言语说明其范围。如果它依赖外部 LLM API 或 OpenClaw 实例，运行成本会很高，不适合在每次 PR 时运行。
- **建议**: 加一个 `tests/README.md` 说明每个测试的范围和运行成本。
- **优先级**: P2

### 2.5 Delta 门禁严格性

#### Issue #10 [HIGH] - Delta 门禁硬规则未在 pipeline 层面强制执行
- **位置**: `SKILL.md` > "硬门禁" vs `orchestrate.skill` > `run()`
- **问题**: `orchestrate.skill` 有 `_check_budget` 对 token/time/cost 做硬检查，但对于 skill 质量 delta 的硬门禁（PassRate、Token delta）没有对应的硬拒绝逻辑。
- **影响**: 门禁承诺形同虚设，一个 delta 不满足条件的 candidate 仍可能进入 deploy。
- **修复建议**: 
  1. 将 `delta_calculator.py` 中的门禁规则封装为 `DeltaGate` 类或纯函数，返回 `(passed, reason)`。
  2. 在 `orchestrate.skill` 的 sandbox 后调用 gate 判断，失败则 `return result` 并标记 `errors`。
- **优先级**: P0

#### Issue #11 [MEDIUM] - benchmark.skill 的 compare 逻辑未展示
- **位置**: `benchmark.skill`
- **问题**: `sandbox.skill` 调用 `benchmark.skill.compare()`，但我们没有读到 `benchmark.skill` 的完整内容（之前只读取了部分）。如果 compare 方法是软门禁，则同样需加固。
- **修复建议**: 检查 `benchmark.skill` 中 `compare()` 的实现，确保其遵守硬门禁规则。
- **优先级**: P1

### 2.6 安全边界

#### Issue #12 [MEDIUM] - `modify_skill_file` 的 target_module 校验在 sandbox 与 deploy 中重复但标准不一
- **位置**: `gate.skill` `_check_scope_lock` vs `sandbox.skill` `_apply_candidate` vs `deploy.skill` `_validate_file_path`
- **问题**: 三层都有路径/scope 校验：
  - gate: 检查 `target_module` 是否在 deny 列表（字符串 in 匹配）
  - sandbox: 检查 `file_path_relative` 是否 traversal（`..`）
  - deploy: 再次检查 traversal + 是否在 skill 目录内
  - 三个层面对齐度不够（gate 用 target_module, sandbox/deploy 用 file_path_relative），且 gate 只检查"是否在 deny 列表"，不检查文件路径 escapes。
- **影响**: 一个 candidate 可能通过 gate（target_module 没命中 deny），但实际在 deploy 里写到了不该写的地方。
- **修复建议**:
  1. 统一 scope 校验为一个 `security.scope_check(candidate, target, policy)` 函数， gate/sandbox/deploy 共用。
  2. 增加 "文件路径必须在 target skill 目录内"的强校验。
- **优先级**: P1

#### Issue #13 [LOW] - evolution-policy.yaml 的 deny 列表缺少注释说明新增项的风控流程
- **位置**: `evolution-policy.yaml`
- **问题**: 文档没有说明"如何将新的 skill 加入 allow 列表"或"deny 列表如何扩展"。
- **建议**: 加注释说明 deny 扩展需要评审 + 至少两层签名（或人工审批）。
- **优先级**: P2

---

## 3. 触发器边界测试查询

### should-trigger (10) — 应触发 ASO pipeline

1. `"帮我把这个 skill 优化一下"`（提到"skill" + "优化"）
2. `"诊断一下 planner 的性能瓶颈"`（提到"诊断" + 技能/组件名）
3. `"把生产 trace 转成测试用例跑一下"`（提到 trace + 测试用例）
4. `"跑一次 ASO 优化流程"`（显式提到 ASO）
5. `"自动演化 workflow 这个 skill"`（提到"自动演化" + 具体 target）
6. `"分析昨天跑的那些 task，找一下哪里慢"`（暗示 trace 分析）
7. `"把 planner 的 benchmark 数据整理一下，走 skill-opt"`（提到 skill-opt + target）
8. `"这个 skill 最近 token 消耗太高，帮我看看怎么优化"`（提到优化 + 迹象）
9. `"你上次说的 skill 优化方案，帮我实际跑一遍"`（上下文中的 ASO 延续）
10. `"用 evolve 的方式来优化下 router 的 prompt"`（提到 evolve + target）

### should-not-trigger (10) — 不应触发 ASO pipeline

1. `"今天的天气怎么样？"` — 普通闲聊
2. `"学一下新的前端框架"` — 学习讨论，无优化意图
3. `"帮我写一段 Python 代码"` — 普通编码任务
4. `"最近有什么新闻？"` — 新闻资讯
5. `"解释一下量子纠缠"` — 知识问答
6. `"谢谢"` — 礼貌回应
7. `"周末有什么活动？"` — 生活类
8. `"帮我翻译这段文字"` — 语言任务
9. `"这首歌好听吗？"` — 主观评价
10. `"ASO 是哪家公司？"` — 知识查询（雇主品牌，非技能优化）

---

## 4. 修复优先级总表

| 优先级 | Issue # | 严重等级 | 简述 | 预估工作量 |
|--------|---------|---------|------|-----------|
| P0 | #1, #2, #5, #10 | HIGH | 默认值一致性 / 触发器收紧 / 硬门禁真正硬起来 | 2-4h |
| P1 | #4, #6, #8, #12 | MEDIUM | 消除重复安全边界 / 统一 CLI 契约 / 补测试 / 统一 scope 校验 | 3-6h |
| P2 | #3, #7, #9, #11, #13 | LOW | NOT 触发说明 / 脚本函数合并 / 测试 README / benchmark 检查 / 扩展注释 | 2-3h |

**P0 风险提示**: Issue #1 和 #10 组合起来意味着目前 pipeline 在文档层面承诺了硬门禁，但实际不会**硬拒绝**不合规 candidate。建议在下一个 patch 中合并修复这两项，并发布一个 patch release note。

---

## 5. 附加观察

- `trace_to_eval.py` 是新加入的工具，它作为 bridge between observe 和 eval_runner，但目前没有文档说明它的输入输出格式。建议在 `optimizer/` 或 `docs/` 下加一个专门的 trace-eval 接口文档。
- `README.md` 存在但内容较长（8962 bytes），SKILL.md 只写了 2003 bytes。建议把详细实现说明从 README 移到 docs/ 下，SKILL.md 只保留触发条件和入口概述。
- `_lib/` 里缺少 `yaml` 的 fallback 说明文档，多个 skill 都用 `try import yaml` 但没记录如果 PyYAML 缺失时的行为。

---

## 6. 触发测试查询（用于后续 skill-opt 测试套件）

```json
{
  "should_trigger": [
    "帮我把这个 skill 优化一下",
    "诊断一下 planner 的性能瓶颈",
    "把生产 trace 转成测试用例跑一下",
    "跑一次 ASO 优化流程",
    "自动演化 workflow 这个 skill",
    "分析昨天跑的那些 task，找一下哪里慢",
    "把 planner 的 benchmark 数据整理一下，走 skill-opt",
    "这个 skill 最近 token 消耗太高，帮我看看怎么优化",
    "你上次说的 skill 优化方案，帮我实际跑一遍",
    "用 evolve 的方式来优化下 router 的 prompt"
  ],
  "should_not_trigger": [
    "今天的天气怎么样？",
    "学一下新的前端框架",
    "帮我写一段 Python 代码",
    "最近有什么新闻？",
    "解释一下量子纠缠",
    "谢谢",
    "周末有什么活动？",
    "帮我翻译这段文字",
    "这首歌好听吗？",
    "ASO 是哪家公司？"
  ]
}
```

---

*报告由 ASO 审计子代理生成，基于 skill-opt 六维度模型。*
