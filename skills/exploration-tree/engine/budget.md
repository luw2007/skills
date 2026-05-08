# Budget & Stop Conditions

控制探索引擎何时停止，防止无限消耗。

## Budget Schema

在 state.json 的 `engine.budget` 字段中持久化：

```json
{
  "max_iterations": 200,
  "max_depth": 5,
  "time_budget_minutes": 480,
  "max_consecutive_failures": 10,
  "stop_on_first_success": true,
  "pause_conditions": ["all_nodes_blocked", "budget_80_percent"],
  "consumed": {
    "iterations": 47,
    "depth_reached": 3,
    "elapsed_minutes": 34,
    "consecutive_failures": 2,
    "successes": 0
  }
}
```

## 停止条件（硬停）

满足任一条件时立即停止循环，不再调度：

| 条件 | 检查 | 动作 |
|------|------|------|
| 迭代耗尽 | consumed.iterations >= max_iterations | stop + report |
| 深度耗尽 | depth_reached >= max_depth | stop + report |
| 时间耗尽 | elapsed_minutes >= time_budget_minutes | stop + report |
| 目标达成 | stop_on_first_success && successes > 0 | stop + celebrate |

## 暂停条件（软停）

满足时暂停并通知用户，等待人工决策：

| 条件 | 检查 | 用户选择 |
|------|------|----------|
| 全部阻塞 | 当前层所有节点 status ∈ {blocked, failed} | 提供新方向 / 放弃 |
| 预算 80% | iterations/max > 0.8 | 追加预算 / 停止 |
| 连续失败 | consecutive_failures >= max | 反思后继续 / 停止 |

## 默认值

用户未指定时的默认预算：

```
--budget 50       → max_iterations=50, time_budget=120min
--budget 200      → max_iterations=200, time_budget=480min
--budget unlimited → max_iterations=10000, time_budget=1440min
```

max_depth 默认 5，max_consecutive_failures 默认 10，stop_on_first_success 默认 true。

## 命令行参数映射

```
/exploration-tree start --budget 200 --depth 4 --timeout 60m --no-stop-on-success
```

- `--budget N` → max_iterations = N
- `--depth N` → max_depth = N
- `--timeout Nm` → time_budget_minutes = N
- `--no-stop-on-success` → stop_on_first_success = false

## Budget Report

停止时输出：

```
═══════════════════════════════════════
📊 Budget Report
═══════════════════════════════════════
迭代: 47/200 (23.5%)
深度: 3/5
时间: 34min/480min (7.1%)
节点: ✅0 ❌12 ⏸️3 💡8
停止原因: all_nodes_blocked (soft pause)
═══════════════════════════════════════
建议: 提供新的搜索方向，或调整约束条件
```
