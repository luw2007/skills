# Node Selection Strategies

决定每轮迭代选择哪个节点进行探索。策略在 state.json 的 `engine.strategy` 字段指定。

## 可用策略

### cost-ordered（默认）

按 (难度低 → 高) 排序，同难度按创建时间排序。

```
优先级 = difficulty ASC, created_at ASC
```

**适用**: 大多数场景。快速排除简单假设，缩小搜索空间。
**原理**: 便宜的验证先做 — 如果 5 分钟能排除一个方向，不要花 1 小时。

### risk-ordered

按 (潜在收益 × 可行性 / 成本) 排序。需要 domain adapter 在 enumerate 时提供 `risk_score`。

```
优先级 = risk_score DESC
risk_score = (impact * probability) / difficulty
```

**适用**: 安全审计。高危路径优先验证。
**要求**: domain adapter 的 enumerate 输出必须包含 `impact` 和 `probability` 字段。

### breadth-first

严格按层级和节点顺序遍历，不跳跃。

```
优先级 = layer_id ASC, node_index ASC
```

**适用**: 需要完整覆盖的场景（如合规审计、全面测试）。
**缺点**: 不利用信息增益剪枝，可能浪费预算在低价值节点上。

### depth-first

选中一个有希望的路径后一直深入，直到成功或失败才回溯。

```
优先级 = depth DESC（优先深入当前活跃路径的子节点）
```

**适用**: 目标明确、路径较窄的场景（如单一 bug 定位）。
**缺点**: 可能在死胡同中浪费大量预算。

## 策略切换

引擎支持运行时切换策略：

- 默认 cost-ordered
- 连续 5 次 probe 都 "failed" → 自动考虑切换（在 reflection 中建议）
- 用户可通过 `/exploration-tree strategy <name>` 手动切换

## select_focus 算法

```python
def select_focus(state, strategy):
    candidates = []
    for layer in state.layers:
        for node in flatten_with_children(layer.nodes):
            if node.status in ("pending", "active"):
                candidates.append(node)

    if not candidates:
        return None  # 触发 reflection

    # 过滤 blocked 节点（除非没有其他选择）
    non_blocked = [n for n in candidates if n.status != "blocked"]
    pool = non_blocked if non_blocked else candidates

    return sort_by_strategy(pool, strategy)[0]
```

## 命令行指定

```
/exploration-tree start --strategy risk-ordered
/exploration-tree strategy depth-first   # 运行时切换
```
