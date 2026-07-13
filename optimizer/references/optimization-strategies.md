# 优化策略库

> **渐进式披露原则**：本文件仅在 Agent 需要深入诊断或遇到特定失败模式时读取。日常优化工作应聚焦于 SKILL.md 正文的简洁指令。

---

## 1. 根因-策略映射表

| 失败根因 | 典型症状 | 优化策略 | 优先级 |
|----------|----------|----------|--------|
| 意图理解错误 | 技能未触发或触发错误技能 | 增强 description 的关键词覆盖；增加边界 few-shot 示例；使用 "Use this skill when..." 开头 | P0 |
| 知识/事实错误 | 输出包含幻觉或过时数据 | 修剪不可靠知识源；强制引用验证步骤；添加 `cite_source` 工具约束；降低 temperature | P0 |
| 工具调用失败 | 工具参数错误、未处理异常、missing required args | 修正工具 description/schema；添加错误处理分支与 `try-catch` 模式；增加重试逻辑（最多 2 次） | P0 |
| 逻辑/推理断裂 | 多步推理链条错误、中间状态丢失 | 引入 chain-of-thought；添加合理性自检步骤；使用 plan-verify-execute 循环 | P1 |
| 鲁棒性不足 | 对边界/对抗输入敏感、空值崩溃 | 对抗样本训练式 prompt tuning；增加输入规范化层（如 JSON schema validation）；添加 fallback 路径 | P1 |
| 效率问题 | 多余步骤、冗长输出、重复工具调用 | 精简 prompt 到 2000 tokens 以内；合并工具调用；设置最大步数限制（如 `max_steps: 10`） | P1 |
| 安全/合规问题 | 注入、越狱、敏感信息泄露 | 加固系统护栏；添加输入/输出过滤器；拒绝处理 PII 数据 | P0 |
| 用户体验问题 | 啰嗦、语气不一致、格式混乱 | 统一输出格式（如 Markdown）；控制长度（< 500 words）；增加共情语句模板 | P2 |

---

## 2. 描述优化模式库（Description Tuning）

在优化技能时，`description` 的质量直接影响触发准确率。参考以下模式：

### 2.1 前置条件明确化

**模式**：清晰定义技能适用的场景和用户意图。

**示例**：
```markdown
# Bad
Use this skill for data visualization.

# Good
Use this skill when the user wants to create charts, graphs, or plots from tabular data.
The input should be a table (CSV, Excel, or structured data).
```

### 2.2 负面示例预防

**模式**：明确说明技能**不应该**处理的情况，减少误触发。

**示例**：
```markdown
# Bad
Generate meeting summaries.

# Good
Use this skill when the user provides a meeting transcript (text with speaker labels and timestamps) and wants a structured summary with action items.

Do NOT use this skill for:
- Simple Q&A about the meeting content (use chat directly)
- One-sentence takeaways (too trivial)
- Transcripts without clear speaker separation
```

### 2.3 近义词覆盖

**模式**：覆盖用户可能使用的同义词和变体，但要避免过度宽泛。

**示例**（对于图表生成）：
```markdown
Keywords: chart, graph, plot, visualize, scatter, line chart, bar chart, histogram, pie chart
```

### 2.4 格式约束注入

**模式**：强制指定输出格式，减少后续处理成本。

**示例**：
```markdown
Always output valid JSON with the following schema:
{
  "chart_type": "bar|line|pie|scatter",
  "data": [...],
  "x_axis": "...",
  "y_axis": "..."
}
```

---

## 3. 上下文重构手术指南（Context Slimming）

当 SKILL.md 正文超过 5000 tokens 时，按以下优先级进行"手术"：

### 3.1 删除清单（Delete）

**删除内容**：
- [ ] 通用知识（如 "JSON is a data format"）
- [ ] 背景介绍和历史沿革
- [ ] 重复声明（同一概念在不同章节出现多次）
- [ ] 显而易见的操作步骤（Agent 已具备的能力）
- [ ] 冗长的示例（超过 5 行的示例应移至 `references/examples/`）

### 3.2 替换清单（Replace）

**替换模式**：
- 将 "ALWAYS do X" → "Do X because Y often causes Z"
- 将 "NEVER do Y" → "Avoid Y as it may lead to Z failure mode"
- 将 "You must..." → "For best results, prefer..."

**示例**：
```markdown
# Before
ALWAYS use the search tool first to get up-to-date information.

# After
Use the search tool first because knowledge cutoff can lead to outdated answers.
```

### 3.3 注入模式（Inject）

对于脆弱工作流，加入检查清单和验证循环：

```markdown
## Safety Checklist (run before every execution)
- [ ] Input is well-formed and within expected bounds
- [ ] All required parameters are present
- [ ] Tool permissions are sufficient
- [ ] Estimated cost is acceptable

## Plan-Verify-Execute Loop
1. **Plan**: Outline the steps and expected intermediate results.
2. **Verify**: After each tool call, check if the output matches expectations.
3. **Execute**: Only proceed when verification passes; otherwise backtrack.
```

---

## 4. 自包含脚本模板（Scripts Extraction）

检测到 Agent 重复编写相同逻辑时，提取为独立脚本。

### 4.1 Python 脚本（PEP 723）

```python
# /// script
# requires-python = ">=3.10"
# dependencies = ["pandas", "openpyxl"]
# ///
"""Data清洗脚本：处理CSV缺失值和数据类型转换"""
import sys
import json
import pandas as pd

def main():
    # 参数从命令行或环境变量获取
    input_path = sys.argv[1] if len(sys.argv) > 1 else os.getenv("INPUT_PATH")
    output_path = sys.argv[2] if len(sys.argv) > 2 else "stdout"

    df = pd.read_csv(input_path)

    # 清洗逻辑
    df = df.dropna(subset=["required_column"])
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    # 输出 JSON 到 stdout
    result = df.to_dict(orient="records")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # 诊断信息到 stderr
    print(f"Processed {len(df)} rows", file=sys.stderr)

if __name__ == "__main__":
    main()
```

**调用方式**（在 SKILL.md 中）：
```markdown
Use the data cleaner script:
```bash
python {baseDir}/scripts/clean_data.py input.csv
```
```

### 4.2 TypeScript 脚本（Deno）

```typescript
#!/usr/bin/env -S deno run --allow-read --allow-write --allow-net
/**
 * 图表配置生成器
 */
interface Config {
  width: number;
  height: number;
  colors: string[];
}

function generateConfig(dataSize: number): Config {
  return {
    width: Math.min(dataSize * 10, 1200),
    height: 600,
    colors: ["#3498db", "#e74c3c", "#2ecc71"],
  };
}

const args = Deno.args;
const inputFile = args[0];
const raw = await Deno.readTextFile(inputFile);
const data = JSON.parse(raw);

const config = generateConfig(data.length);
console.log(JSON.stringify(config, null, 2));
```

**调用方式**：
```markdown
```bash
deno run --allow-read {baseDir}/scripts/generate_chart_config.js data.json
```
```

---

## 5. 评估 harness 构建指南

### 5.1 测试用例结构

每个测试用例是一个 JSON 对象：

```json
{
  "id": "test-001",
  "description": "Normal case: valid CSV with numeric data",
  "prompt": "Generate a bar chart from the attached CSV file.",
  "files": ["test-data/sample.csv"],
  "expected_output": {
    "format": "json",
    "must_contain": ["chart_type", "data"],
    "must_not_contain": ["error", "undefined"]
  },
  "assertions": [
    "output is valid JSON",
    "output.chart_type in ['bar', 'line', 'pie']",
    "len(output.data) > 0"
  ],
  "severity": "medium"
}
```

### 5.2 评估 runner 实现

在 OpenClaw 中，评估 runner 可以通过以下方式构建：

```bash
#!/usr/bin/env bash
# eval_runner.sh
SKILL_PATH="$1"
EVALS_FILE="$2"
OUTPUT_DIR="$3"

mkdir -p "$OUTPUT_DIR"

jq -c '.[]' "$EVALS_FILE" | while read test; do
  test_id=$(echo "$test" | jq -r '.id')
  echo "Running test: $test_id"

  start=$(date +%s)
  output=$(openclaw agent \
    --message "$(echo "$test" | jq -r '.prompt')" \
    --attach "$(echo "$test" | jq -r '.files[]')" \
    2>&1)
  end=$(date +%s)

  echo "$output" > "$OUTPUT_DIR/${test_id}_output.txt"

  # 计时
  duration=$((end - start))
  echo "$duration" > "$OUTPUT_DIR/${test_id}_time.txt"

  # TODO: 调用 assert 检查器验证输出
  # python scripts/assertion_checker.py "$test" "$OUTPUT_DIR/${test_id}_output.txt"
done

# 汇总统计
python scripts/benchmark_aggregator.py "$OUTPUT_DIR" > "$OUTPUT_DIR/benchmark.json"
```

---

## 6. 触发校准实施细节

### 6.1 生成触发测试查询

使用 LLM 为目标 skill 生成 20 个测试查询：

```markdown
Based on the skill description below, generate 20 test queries:

Skill description:
<original description>

Output format (one query per line):
[should-trigger] query text...
[should-not-trigger] query text...
```

### 6.2 自动化校准流程

```bash
#!/usr/bin/env bash
# calibrate_triggers.sh

# 1. 生成 query list（如果不存在）
if [ ! -f "trigger_queries.txt" ]; then
  python scripts/query_generator.py --skill-path . --output trigger_queries.txt
fi

# 2. 测试每个 query 是否触发 skill
> trigger_results.csv
while IFS='|' read -r type query; do
  echo "Testing: $query"
  # 调用 openclaw agent 并检查 trace
  triggered=$(openclaw agent --message "$query" --trace 2>&1 | grep -c "skill-opt" || true)
  expected=$([ "$type" = "should-trigger" ] && echo "1" || echo "0")
  echo "$type,$query,$triggered,$expected" >> trigger_results.csv
done < <(awk -F' ' '{print $1" "$2}' trigger_queries.txt)

# 3. 计算准确率
python scripts/trigger_metrics.py trigger_results.csv
```

### 6.3 校准终止条件

- 验证集准确率 ≥ 85%
- 训练集 vs 验证集差距 ≤ 15%
- 迭代不超过 10 次（防过拟合）

---

## 7. Delta 决策门禁规则

`delta_calculator.py` 输出 verdict 的逻辑：

```python
def verdict(delta_pass, delta_token_pct):
    if delta_pass <= 0:
        return "failed"  # 通过率不升反降，失败
    if delta_token_pct > 20 and delta_pass < 0.05:  # token 增 >20% 且通过率提升 <5%
        return "failed"  # 性价比太低
    if delta_pass > 0 or delta_token_pct < 0:
        return "improved"
    return "neutral"
```

**自动回滚**：如果某个迭代的 verdict 是 `failed`，立即：
1. 恢复上一个迭代的 `SKILL.md`
2. 将失败迭代标记为 `blocked`
3. 记录原因到 `regression_log.md`
4. 停止进一步迭代

---

## 8. 迭代快照管理

每次迭代创建独立目录 `workspace/iteration-<N>/`：

```
iteration-1/
├── SKILL.md          # 该迭代的 skill 定义
├── benchmark.json    # 该迭代的评估汇总
├── optimization_report.md  # 修改与诊断
├── eval_results/     # 所有测试用例的详细输出
└── delta.json        # 与上一迭代的 Delta 对比
```

提供 `snapshot_manager.py`（P1 优先级）实现：
- `create_snapshot(iteration)` - 创建快照
- `list_snapshots()` - 列出所有迭代
- `restore(iteration)` - 恢复到指定迭代

---

## 9. 安全边界与约束

**绝对禁止的行为**：
- ❌ 放宽原技能的安全护栏（如移除内容过滤器）
- ❌ 删除或弱化断言（即使它们导致失败）
- ❌ 增加超过 2000 tokens 的正文内容
- ❌ 引入未经验证的第三方依赖（如新的 npm 包）
- ❌ 硬编码 API 密钥或敏感信息

**变更追溯要求**：
- 每条修改必须关联到具体失败案例 ID
- 每条新增指令必须证明其 token 成本 ≤ 它修复的错误收益
- 每次 Delta 计算必须保存原始数据供审计

---

## 10. OpenClaw 工具调用速查

| 任务 | 推荐工具 | 示例命令 |
|------|----------|----------|
| 读取文件 | `read` | `read(path="/path/to/file")` |
| 写入快照 | `write` | `write(path="/path", content="...")` |
| 运行评估 | `exec` | `exec(command="bash eval_runner.sh ...")` |
| 获取轨迹 | `sessions_history` | `sessions_history(sessionKey="...")` |
| 创建提案 | `skill_workshop` | `skill_workshop(action="create", ...)` |

---

## 11. 常见失败模式与应对

| 失败模式 | 识别方法 | 应对策略 |
|----------|----------|----------|
| 评估用例无法机器验证 | Assertion 需要使用自然语言判断 | 重写为结构化断言（JSON schema, regex, exact match） |
| Trigger 校准过拟合 | Train acc >> Val acc (>0.2 gap) | 简化 description，移除训练集特例 |
| 迭代不收敛 | 多次迭代 Delta 在 0 附近震荡 | 停止优化，保持当前版本；可能需要人工介入 |
| Token 消耗暴增 | 单次迭代 token 增加 >30% | 强制上下文压缩，移除冗长示例 |
| 回滚循环 | 同一修改触发多次回滚 | 永久禁止该修改方向，标记为"已探索但无效" |

---

## 12. 持续改进建议

- **定期重跑评估**：每周用新的用户查询运行一次优化器，捕获新的失败模式
- **更新策略库**：将本文件标记为 `P0` 的策略定期回顾，根据实际效果调整优先级
- **社区贡献**：将有效的优化策略回传给 agentskills.io 社区

---

**最后提醒**：Optimization is not about chasing perfect metrics. It's about making sustainable, measurable improvements while respecting the skill's original purpose and safety boundaries.
