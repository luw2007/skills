# Domain Adapter Interface

Domain adapter 定义了探索引擎在特定问题领域中**如何**执行探索动作。
引擎负责**何时**和**按什么顺序**探索；adapter 负责具体的验证方法。

## 文件约定

每个 domain adapter 是 `domains/<name>.md` 文件，包含以下四个 section。

## 接口契约

### enumerate

```yaml
enumerate:
  trigger: 引擎需要生成新层的候选节点时调用
  input:
    goal: string          # 最终目标
    constraints: string[] # 不可违反的条件
    confirmed_facts: string[]  # 已确认事实
    excluded_paths: string[]   # 已排除的方向（附原因）
    depth: int            # 当前层深度
  output:
    nodes:
      - name: string      # 路径名称
        hypothesis: string # 核心假设
        difficulty: 1|2|3  # ⭐/⭐⭐/⭐⭐⭐
        method: string     # 验证手段描述
        impact: float?     # 0-1, 用于 risk-ordered 策略
        probability: float? # 0-1, 用于 risk-ordered 策略
  constraints:
    - 输出 3-8 个候选节点
    - 包含至少 1 个 difficulty=1 的节点（确保有低成本选项）
    - 不重复 excluded_paths 中已排除的方向
```

### probe

```yaml
probe:
  trigger: 引擎对单个 pending 节点执行浅探测
  input:
    node: { name, hypothesis, method }
    context:
      goal: string
      confirmed_facts: string[]
      parent_evidence: string?  # 父节点的证据（如果是子节点）
  output:
    status: "success" | "failed" | "blocked"
    actual: string        # 实际观察到的现象
    evidence: string?     # 关键证据（精简）
    conclusion: string    # 结论
    exclusion:            # 仅 status=failed 时
      type: "principle" | "implementation" | "constraint"
      reason: string
  constraints:
    - 单次 probe 耗时控制在 5 分钟以内
    - 使用最轻量的验证手段（grep > read > execute）
    - 不做完整实现，只判断可行性
  tools_allowed:
    - Read（读源码文件）
    - Bash（grep, find, wc, git log 等只读命令）
    - WebSearch（查找已知信息）
    - Agent(Explore)（委托搜索）
```

### drill

```yaml
drill:
  trigger: probe 返回 success 后，需要深入展开子问题
  input:
    node: { name, hypothesis, method, evidence }
    context:
      goal: string
      confirmed_facts: string[]
  output:
    children:
      - name: string
        hypothesis: string
        difficulty: 1|2|3
        method: string
    evidence: string?     # drill 过程中的额外发现
    conclusion: string?   # 如果 drill 本身就得出了最终结论
  constraints:
    - 产生 2-5 个子节点
    - 子节点应比父节点更具体
    - 如果 drill 直接达成 goal → 设 conclusion，引擎识别为终态
  tools_allowed:
    - 全部工具（包括 Edit/Write 如果需要产出 PoC）
```

### reflect

```yaml
reflect:
  trigger: 当前层所有节点 resolved（全部 success/failed/blocked）
  input:
    failed_nodes: [{ name, exclusion }]
    success_nodes: [{ name, evidence, conclusion }]
    blocked_nodes: [{ name, reason }]
    goal: string
    confirmed_facts: string[]
  output:
    common_failure_pattern: string?  # 失败节点的共性
    overlooked_assumptions: string[] # 被忽视的前提假设
    new_paths:
      - name: string
        hypothesis: string
        difficulty: 1|2|3
    updated_facts: string[]  # 新确认的事实（追加到 confirmed_facts）
  constraints:
    - 不重复已失败的方向
    - 至少产出 2 个新路径
    - 如果找不到新方向 → 输出 "search_exhausted" 信号
```

## 编写新 adapter

1. 复制 `domains/_template.md`（如有）或参考 `domains/kernel-audit.md`
2. 填充四个 section，每个 section 描述：
   - 该领域中这个动作的具体含义
   - 推荐使用的工具和命令
   - 典型输出示例
3. 在 enumerate 中定义初始攻击面 / 搜索空间
4. 测试：`/exploration-tree start --domain <name> --budget 5` 运行 5 轮验证

## 内置 adapters

| Domain | 文件 | 用途 |
|--------|------|------|
| kernel-audit | `domains/kernel-audit.md` | Linux 内核漏洞模式搜索 |
| codebase-review | `domains/codebase-review.md` | 通用大代码库质量/安全审计 |
