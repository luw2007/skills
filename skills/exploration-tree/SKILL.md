---
name: exploration-tree
description: |
  自主探索树引擎。适用于需要系统性穷举、验证、排除的复杂问题求解。
  支持手动和自主两种模式：手动模式逐步记录；自主模式通过 ScheduleWakeup
  持续运行"广度枚举 → 选择 → 深入 → 回溯"循环，直到找到目标或耗尽预算。
  触发词："探索树"、"exploration tree"、"自主探索"、"long run explore"。
version: 1.0.0
---

# 探索树（Exploration Tree）

树状探索引擎，支持手动记录和自主循环两种模式。

## 命令

### 手动模式（原有功能）

- `/exploration-tree` — 初始化探索，确认目标后记录路径
- `/exploration-tree status` — 查看当前树状态
- `/exploration-tree reflect` — 手动触发反思，生成新方向

### 自主模式（新增）

- `/exploration-tree start` — 启动自主探索循环
- `/exploration-tree pause` — 暂停循环
- `/exploration-tree resume` — 恢复循环
- `/exploration-tree iterate` — 内部命令，执行单轮迭代（由 ScheduleWakeup 触发）
- `/exploration-tree strategy <name>` — 切换节点选择策略

### start 参数

```
/exploration-tree start --domain <name> --goal "<目标>" [--budget N] [--strategy <name>] [--depth N] [--timeout Nm] [--source-path /path]
```

| 参数 | 必须 | 默认 | 说明 |
|------|------|------|------|
| --domain | 是 | - | domain adapter 名称（对应 domains/<name>.md） |
| --goal | 是 | - | 探索目标（含成功标准） |
| --budget | 否 | 50 | 最大迭代次数 |
| --strategy | 否 | cost-ordered | 节点选择策略 |
| --depth | 否 | 5 | 最大探索深度 |
| --timeout | 否 | 120m | 时间预算 |
| --source-path | 否 | cwd | 目标代码/数据的路径 |
| --no-stop-on-success | 否 | false | 找到第一个成功后继续探索 |

### 示例

```bash
# 内核漏洞搜索
/exploration-tree start --domain kernel-audit --goal "Find splice page-cache write primitive reachable from user namespace" --budget 200 --source-path ~/linux

# 代码库审计
/exploration-tree start --domain codebase-review --goal "Find all SQL injection vectors" --budget 50 --source-path .

# 通用复杂问题（无 domain adapter 时使用内置通用逻辑）
/exploration-tree start --goal "为什么应用启动需要 8 秒" --budget 30
```

## 工作流

### 手动模式

1. **广度枚举** — 列出当前层所有候选路径 + 难度评估
2. **评估排序** — 按 (可行性 × 收益 / 成本) 排序
3. **深度钻探** — 选中目标后全力投入
4. **失败回溯** — 标记排除原因，选下一个
5. **层级耗尽** — 触发反思，生成新层
6. **持久化** — 每次变更写入 state.json

### 自主模式

在手动模式的基础上，由引擎自动执行选择和迭代：

1. 读取 state.json → 按 strategy 选择 focus 节点
2. 调用 domain adapter 的 probe/drill/reflect 动作
3. 更新 state.json
4. 检查 budget → 未耗尽则 ScheduleWakeup 继续
5. 每轮之间保持 90s 间隔（prompt cache warm）

详见 `engine/loop.md`。

## 文件布局

```
<project_root>/exploration/
├── <task-name>.md           # 探索树日志（人类可读）
├── <task-name>.state.json   # 机器可读状态
└── <task-name>.lock         # 并发锁
```

## Domain Adapters

Domain adapter 定义了特定领域的探索方法。详见 `domains/README.md`。

内置 adapters:
- `kernel-audit` — Linux 内核漏洞模式搜索
- `codebase-review` — 通用大代码库审计

无 `--domain` 参数时，引擎使用内置通用逻辑（直接向 LLM 请求 enumerate/probe/reflect）。

## 资源引用

- **`engine/loop.md`** — 自主循环协议（ScheduleWakeup 调度）
- **`engine/budget.md`** — 停止条件规范
- **`engine/strategies.md`** — 节点排序策略
- **`domains/README.md`** — domain adapter 接口规范
- **`references/format.md`** — 完整格式规范
- **`references/example.md`** — 示例
