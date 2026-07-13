# ASO — Automatic Skill Optimizer for OpenClaw

ASO 是一个面向 OpenClaw 的**全自动技能演化管道**。它把生产环境的会话 Trace 转化为可复用的技能改进方案，并通过数据驱动的量化门禁完成部署。

核心思路是让技能“自己看懂自己哪里不好”，再自动生成更优版本、跑测试验证、最后原子写入并保留下滚能力。

---

## 目前状态

> ⚠️ **实验性阶段**
>
> - 基础骨架、测试套件、部署/回滚机制已就绪
> - `gate` / `sandbox` 的 Delta 量化门禁仍在集成中
> - `tdo_calibrator` 的真实训练逻辑待完善
>
> 请在非生产环境充分验证后再启用自动部署流程。

---

## 目录结构

```
aso/
├── README.md                  # 本项目说明
├── SKILL.md                   # OpenClaw 技能入口声明
├── config                     # 运行时配置
├── evolution-policy.yaml      # 安全边界 & Target 白名单
├── trace_schema.yaml          # Trace 数据格式定义 v1
├── trace_schema.json          # 同上，JSON 版本
├── trace_to_eval.py           # 将失败 Trace 转换为测试用例
├── orchestrate.skill          # 编排入口（ASO / bilevel 双策略）
├── observe.skill              # 生产 Trace 采集
├── diagnose.skill             # 瓶颈统计 & 优先级报告
├── gate.skill                 # 结构校验 & 安全策略检查
├── sandbox.skill              # 沙箱隔离 + 回归对比
├── report.skill               # 标准化 Evolution Proposal 生成
├── deploy.skill               # 原子写入 + 热加载标记
├── rollback.skill             # 基于 manifest 的版本回滚
├── benchmark.skill            # 多维度评分模块
│
├── generator/
│   ├── __init__.py
│   ├── registry.py            # 生成器注册中心
│   ├── bilevel.py             # 4 轮 LLM 对话生成器（ evolve 兼容）
│   └── skill_opt_refactor.py   # TDO 重构器（ASO 核心）
│
├── optimizer/
│   ├── delta_calculator.py    # Pass Rate / Token 量化计算
│   ├── eval_runner.py         # 测试套件执行 & 基线对比
│   ├── snapshot_manager.py    # 技能快照管理
│   ├── tdo_calibrator.py      # 触发器词校准 & 指令精简
│   └── references/
│       └── optimization-strategies.md
│
├── _lib/
│   ├── oc_llm_client.py       # OpenClaw LLM 调用封装
│   ├── oc_session_reader.py   # 会话 Trace 读取
│   ├── manifest_utils.py      # 部署 manifest 管理
│   ├── path_utils.py          # 路径工具
│   ├── lock_utils.py          # 并发锁
│   └── time_utils.py          # 时间工具
│
├── evals/
│   └── aso_self_evals.json    # 内建自检测试用例
│
├── state/                     # 运行时状态目录
│   ├── trace_store.json       # 本地 Trace 存储
│   └── manifests.json         # 部署历史 & 备份记录
│
├── tests/
│   └── test_integration.py    # 集成测试
│
└── scripts/
    # （占位，用于未来发布后续工具脚本）
```

---

## 核心流程

ASO 的工作流是一个 5 步闭环：

```
Observe → Diagnose → Generate → Gate + Sandbox → Report & Deploy
   ↑                                                    |
   └────────────── Rollback ←─────────────────────────────┘
```

| 阶段 | 职责 |
|------|------|
| **Observe** | 从 `sessions_history` 或本地 `state/trace_store.json` 采集生产 Trace |
| **Diagnose** | 统计工具效率、任务质量、成功率、上下文利用率，输出优先级报告 |
| **Generate** | 根据策略生成候选方案（LLM 4 轮对话 or TDO 重构） |
| **Gate + Sandbox** | 跑测试、计算 Delta、校验策略门禁 |
| **Report & Deploy** | 生成标准 Proposal，人工审批后原子写入，失败自动回滚 |

---

## 策略模式

通过 `strategy` 参数选择生成策略：

| 策略 | 说明 |
|------|------|
| `bilevel` | 传统 evolve 行为。LLM 做 Explore → Critique → Specify → Generate 4 轮对话 |
| `aso` | ASO 核心。触发词校准 + 指令精简 + 脚本提取，输出极简 SKILL.md |

默认使用 `aso`。

```python
from aso.orchestrate import run

# ASO 策略
result = run(target="planner", strategy="aso")

# 兼容 evolve 的 bilevel 策略
result = run(target="workflow", strategy="bilevel")
```

---

## 快速开始

### 环境要求

- Python 3.10+
- OpenClaw 运行时
- 可用的 LLM 配置（通过 OpenClaw 会话机制）

### 安装

```bash
# 克隆仓库
git clone https://github.com/zhbcher/aso.git
cd aso

# 如果是 OpenClaw 内部使用，软链到 skills 目录
# ln -s /path/to/aso ~/.openclaw/workspace/.agents/skills/aso
```

### 配置

**`evolution-policy.yaml`** 是安全边界，决定哪些 Target 允许被自动演化，哪些坚决不动：

```yaml
policy:
  allow:
    - planner
    - workflow
    - prompt
    - memory
    - skill
    - router

  deny:
    - runtime
    - gateway
    - scheduler
    - kernel
    - evolution-policy.yaml
    - trace_schema.yaml
    - openclaw.json
    - secret.json
    - AGENTS.md
    - SOUL.md
    - USER.md
    - MEMORY.md
```

> 不要对 deny 列表中的目标启用自动演化。修改此文件本身需要人工介入。

### 运行

```python
from aso.orchestrate import run

# 基本运行
result = run(target="planner", strategy="aso")

# 查看量化 delta
print(result["proposal"]["delta"])
```

**`trace_to_eval.py`** 用于把真实失败 Trace 批量转成测试用例：

```bash
python3 trace_to_eval.py --input state/trace_store.json --output evals/aso_self_evals.json
```

---

## 测试

```bash
# 运行集成测试
python3 tests/test_integration.py
```

集成测试涵盖：observe 采集、diagnose 评分、gate 校验、sandbox 对比、deploy 原子写入、rollback 回滚等核心路径。

自检测试用例外置在 `evals/aso_self_evals.json`，由 `eval_runner.py` 加载执行。

---

## 量化门禁（Delta Gate）

部署前的硬门槛：

| 指标 | 阈值 |
|------|------|
| Pass Rate 提升 | ≥ +1% |
| Token 消耗降低 | ≥ -5% |
| 或条件 | Pass Rate 提升 ≥ 5% 时，允许 Token 小幅上升 |

不满足门禁的候选会被直接拒绝，不会进入 deploy 阶段。

---

## 安全模型

ASO 的安全设计围绕三个要点：

1. **Target 白名单** — 只有 `evolution-policy.yaml` 中 `allow` 列出的目标才能被演化
2. **敏感文件硬保护** — 配置文件、系统提示、用户信息等不可自动修改
3. **原子写入 + 自动回滚** — 所有部署写入前生成 manifest 备份，失败立即回滚到上一个稳定版本

---

## 与 evolve / skill-opt 的关系

| 维度 | ASO | evolve | skill-opt |
|------|-----|--------|-----------|
| 数据源 | 生产 Trace + 自我测试 | 生产 Trace | 预设 Evals |
| 生成策略 | LLM + TDO 双引擎 | LLM 4 轮对话 | TDO 重构 |
| 验证门禁 | Delta 量化（严格） | 沙箱 + 分数门槛 | 手工评估 |
| 自动化程度 | 全自动闭环 | 半自动 | 手动触发 |

ASO 是 evolve 和 skill-opt 的融合，继承了 evolve 的实时诊断能力和 skill-opt 的 TDO 重构思路。

---

## 贡献指南

我们欢迎 Issue 和 Pull Request。提交前请注意：

- 代码遵循 PEP 8
- 新功能需要补充对应测试用例（见 `tests/test_integration.py`）
- 修改安全边界逻辑（`evolution-policy.yaml` 或 `_lib/manifest_utils.py`）需要充分说明影响范围
- 提交信息建议遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范

### 开发环境

```bash
# 克隆并准备
git clone https://github.com/zhbcher/aso.git
cd aso

# 确认依赖（本项目的 Python 依赖尽量标准库 + OpenClaw 提供）
python3 -m pytest tests/test_integration.py
```

### 建议流程

1. Fork 本仓库
2. 创建特性分支 `git checkout -b feat/your-feature`
3. 提交修改 `git commit -m 'feat: your feature'`
4. 推送到分支 `git push origin feat/your-feature`
5. 开启 Pull Request

---

## 常见问题

**Q: ASO 会自动修改我的 AGENTS.md / SOUL.md 吗？**

不会。这些文件在 `evolution-policy.yaml` 的 `deny` 列表中，不会被自动演化。修改它们需要人工介入。

**Q: 为什么我的 Skill 没有被 ASO 处理？**

检查 `evolution-policy.yaml` 的 `allow` 列表，确认目标名称匹配。`generator_scopes` 中的 `allowed_targets` 会进一步限制每个策略能操作的范围。

**Q: 回滚会丢失新功能吗？**

不会。ASO 的 deploy 模块会先备份旧版本，rollback 只是恢复备份。可以先对比再决定是否重新部署。

---

## License

MIT
