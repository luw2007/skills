# Autonomous Loop Protocol

exploration-tree 的自主循环引擎。通过 ScheduleWakeup 在 Claude Code 会话内持续运行，
每轮执行一个原子探索动作，直到目标达成或预算耗尽。

## 激活

用户调用 `/exploration-tree start` 时：

1. 解析参数（goal, domain, budget, strategy）
2. 初始化 state.json（或从已有状态恢复）
3. 加载 domain adapter（从 `domains/<name>.md`）
4. 执行第一轮迭代
5. 调用 ScheduleWakeup 调度下一轮

## 每轮迭代协议

```
iteration(state, domain):
  node = select_focus(state, strategy)

  if node is NULL:
    # 当前层全部 resolved
    reflection = domain.reflect(state.current_layer)
    new_layer = create_layer(reflection.new_paths)
    state.layers.append(new_layer)
    state.current_layer += 1
    node = select_focus(state, strategy)

  if node.status == "pending":
    result = domain.probe(node, state.context)

    # === SOUNDNESS GATE ===
    # "failed" 标记需要通过完备性检查，防止错误排除
    if result.status == "failed":
      gate = soundness_check(result, node, state)
      if not gate.passed:
        result.status = "blocked"
        result.conclusion += " [SOUNDNESS GATE: " + gate.reason + "]"
        node.blocked_reason = gate.reason

    node.status = result.status  # "success" | "failed" | "blocked"
    node.actual = result.actual
    node.evidence = result.evidence
    node.conclusion = result.conclusion

    # === 排除粒度与假设标注 ===
    if node.status == "failed":
      # 排除的是函数还是子系统？子系统级排除需要所有入口点打勾
      node.exclusion_scope = result.exclusion_scope  # "function" | "subsystem"
      node.excluded_paths = result.excluded_paths    # ["TX", "RX", ...] 哪些方向已排除
      node.unverified_assumptions = result.unverified_assumptions  # [ASSUMPTION] 列表
      # 子系统级排除必须有完整入口点清单
      if node.exclusion_scope == "subsystem" and not result.all_entry_points_checked:
        node.status = "blocked"
        node.blocked_reason = "子系统级排除需要所有入口点逐一确认"

    if node.status == "success" and node needs drill:
      node.children = domain.drill(node, state.context)
      node.status = "active"

  elif node.status == "active":
    # 已展开子节点，选择子节点中的 pending 继续
    child = select_focus_in(node.children, strategy)
    if child:
      result = domain.probe(child, state.context)
      update(child, result)

  state.iteration += 1
  state.updated_at = now()
  persist(state)

  budget_check = check_budget(state)
  if budget_check.exhausted:
    report_and_pause(state, budget_check.reason)
  else:
    schedule_next(state)
```

## 排除协议（Elimination Protocol）

### 规则 1：排除粒度

- **可以排除**：一个具体函数/路径（如 `rxkad_verify_packet` 的 RX decrypt 方向）
- **不可以排除**：一整个子系统（如 rxkad），除非该子系统的所有入口点都已逐一检查
- 每个子系统维护入口点清单（TX/RX/error/encap），逐一打勾才能整体排除

### 规则 2：排除必须包含"未验证假设"清单

每次标记 `failed` 时，result 必须包含：
```
excluded_paths: ["RX"]           # 排除的是哪条路径
unverified_assumptions:          # 未验证假设列表
  - "[ASSUMPTION] TX 路径（secure_packet）未检查是否对 splice 页做就地加密"
  - "[ASSUMPTION] loopback 发送是否保留原始页引用"
verified_facts:                  # 已验证事实（附代码行号）
  - "rxkad_verify_packet_1:460 使用 sg,sg 就地解密"
  - "recvmsg.c:158 调用 verify_packet"
```

如果 `unverified_assumptions` 非空 → 状态自动降级为 `blocked`。

### 规则 3：排除后反向探针（30 秒检查）

每排除一个候选后，立即执行反向探针：
```bash
# 检查是否存在未审计的对称函数
grep -rn "{subsystem}_secure\|{subsystem}_encrypt\|{subsystem}_prepare" $KERNEL_SRC/net/
grep -rn "{subsystem}_send\|{subsystem}_xmit\|{subsystem}_output" $KERNEL_SRC/net/
```
如果发现未审计的 TX/send 对称函数 → 重新打开候选为 `blocked`。

### 规则 4：排除粒度强制（引擎层）

迭代协议中的 `exclusion_scope` 字段强制执行：
- `exclusion_scope: "function"` — 只排除特定函数的特定方向，不影响同子系统其他入口
- `exclusion_scope: "subsystem"` — 需要 `all_entry_points_checked: true`，否则自动降级为 `blocked`

## ScheduleWakeup 调度策略

| 场景 | delay | 理由 |
|------|-------|------|
| probe 完成，下一节点就绪 | 90s | 保持 prompt cache warm（5min TTL 内） |
| drill 完成，产生了子节点 | 90s | 同上 |
| 上轮执行了重计算 | 270s | 仍在 cache 窗口内，给系统喘息 |
| 触发了 reflection | 180s | reflection 需要更多思考 token |
| 所有节点 blocked | 1200s | 无进展，低频轮询等待外部输入 |
| budget >80% 消耗 | 不调度 | 暂停，报告给用户 |

## ScheduleWakeup 调用

```
ScheduleWakeup({
  delaySeconds: <按上表选择>,
  reason: "<当前状态的一句话描述>",
  prompt: "/exploration-tree iterate"
})
```

`/exploration-tree iterate` 是内部子命令，触发下一轮迭代。

## 暂停与恢复

**暂停** (`/exploration-tree pause`):
- 将 `state.engine.mode` 设为 `"paused"`
- 不调用 ScheduleWakeup
- 输出当前进度摘要

**恢复** (`/exploration-tree resume`):
- 将 `state.engine.mode` 设为 `"autonomous"`
- 立即执行一轮迭代
- 恢复 ScheduleWakeup 调度

## 并发安全

遵循 references/format.md 中的 .lock 协议。每轮迭代开始获取锁，结束释放。
如果锁被其他 session 持有且未超时，本轮跳过（ScheduleWakeup 90s 后重试）。

## 错误恢复

- domain.probe 抛异常 → 标记节点为 "blocked"，记录错误，继续下一节点
- state.json 损坏 → 从 .md 日志重建（.md 是 append-only 的人类可读备份）
- 连续 N 次失败（N = budget.max_consecutive_failures）→ 触发 forced reflection

## Soundness Gate（排除完备性校验）

每次 probe 返回 "failed" 时，在接受该状态之前执行以下校验。
**任一项未通过 → 强制改为 "blocked"。**

```
soundness_check(result, node, state):
  checks = []

  # 1. CALLER 完备性
  if result.evidence 中未列出目标函数的所有调用者:
    checks.append("未穷举 caller — 只验证了部分入口路径")

  # 2. 路径独立性
  if result.conclusion 含 "因为 output/发送端做了 X，所以 input/接收端也安全":
    checks.append("input/output 是独立入口，不能互相推导安全性")

  # 3. 归纳谬误检测
  keywords = ["通常", "一般", "正常情况下", "normally", "typically", "in general"]
  if any(k in result.conclusion for k in keywords):
    checks.append("含模糊限定词，说明分析覆盖不完备")

  # 4. splice/零拷贝检查
  if node 涉及 in-place write/decrypt 且 evidence 未提及 splice/vmsplice/sendfile:
    checks.append("未验证 splice 零拷贝路径是否可到达")

  # 5. encap/tunnel 检查
  if node 涉及网络协议 input 函数且 evidence 未检查 UDP encap / tunnel rcv:
    checks.append("未验证独立接收路径（UDP encap / tunnel）")

  if checks:
    return { passed: false, reason: "; ".join(checks) }
  return { passed: true }
```

### Soundness Gate 的意义

这是从 dirtyfrag (CVE-2026-43284) 的漏洞发现教训中提炼的规则：

- 探索树曾因为 "esp_output 替换了 frag 页" 就推断 "esp_input 处理的都是安全页面"
- 实际上 UDP encap 接收路径绕过了 esp_output，splice 文件页直接到达 esp_input
- 错误根因：从单条路径的属性归纳推广到所有路径，没有穷举入口点

Soundness Gate 确保 **排除一个路径必须是 sound 的**（证明所有入口都安全），
不能只证明最常见入口安全。宁可多一些 "blocked" 节点消耗额外迭代，
也不能错误排除真正的漏洞路径。
