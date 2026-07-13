# ASO CLI 契约

以下脚本构成 ASO 的脚本层入口。所有入口均遵循统一契约：
- `--help` 可用
- 机器可读输出写 stdout，诊断信息写 stderr
- 失败时返回非 0 退出码并附带错误码语义

## 公共约定

| 参数 | 语义 |
|------|------|
| `--skill-path` | 目标 skill 目录 |
| `--evals` | eval cases 路径 |
| `--output` | 产出目录 / 文件路径 |
| `--input` | 输入 trace 路径 |
| `--skill-name` | skill 元数据（可选） |

## 入口索引

| 脚本 | 用途 | 必选参数 | stdout | stderr |
|------|------|---------|--------|--------|
| `optimizer/eval_runner.py` | 跑 eval 并输出 benchmark | `--skill-path`, `--evals`, `--output` | benchmark JSON | 进度 / 汇总 |
| `optimizer/delta_calculator.py` | 计算 baseline vs new 的 delta | `--new-result`, `--baseline-file` | delta JSON | 错误 |
| `trace_to_eval.py` | 将失败 trace 转为 eval cases | `--input`, `--output` | 结果 JSON | 错误 |
