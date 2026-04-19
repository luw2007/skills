---
name: skill-iter
description: |
  Skill 自迭代能力评审与改进工具。
  评估任意 SKILL.md 是否具备自迭代闭环能力，输出结构化评分报告与改进建议。
  可作为 skill 质量门禁集成到 CI 或编排器的 post-execution 阶段。
  触发词：skill 评审、自迭代检查、skill audit、skill improve、技能改进。
---

# Skill Iter — 自迭代能力评审标准

评估一个 Skill 是否具备"自己让自己变好"的能力，输出结构化评分与可操作的改进建议。

## 核心理念

自迭代不是一个功能，而是三层递进的能力：

| 层级 | 名称 | 本质 | 最低要求 |
|------|------|------|----------|
| L1 | 运行时自修复 | 边执行边修正过时步骤 | SKILL.md 中明确授权 Agent 就地修复 |
| L2 | 执行后经验沉淀 | 每次执行的教训自动积累 | 有 Lessons Learned 章节 + 触发条件 + 合并策略 |
| L3 | 跨 Skill 知识联动 | 一个 skill 的经验惠及其他 skill | 经验可被外部 skill 引用或编排器聚合 |

## 评审维度（7 项）

### D1: 反馈采集 — 是否有数据进来

| 等级 | 标准 |
|------|------|
| ❌ 缺失 | 无任何执行反馈机制 |
| ⚠️ 基础 | 仅记录成功/失败 |
| ✅ 达标 | 采集结果状态、轮数、错误次数、是否阻塞 |
| 🌟 优秀 | 额外采集对话轨迹摘要、耗时分布、工具调用统计 |

**检测方法**：检查 SKILL.md 是否有自检/回顾阶段，检查配套脚本/代码中是否有 `collect_feedback` 或等效逻辑。

### D2: 触发判定 — 不是每次都分析，而是值得时才分析

| 等级 | 标准 |
|------|------|
| ❌ 缺失 | 无触发逻辑，从不分析 |
| ⚠️ 基础 | 仅失败时分析 |
| ✅ 达标 | 失败 + 阻塞 + "成功但低效"（轮数/耗时超阈值）均触发 |
| 🌟 优秀 | 支持自定义触发规则，可通过配置调整阈值 |

**关键公式**：
```python
def should_improve(feedback) -> bool:
    if feedback.has_error or feedback.blocked or feedback.failed:
        return True
    return feedback.turns_used > THRESHOLD  # 成功但低效
```

### D3: 分析能力 — 能从轨迹中提取可操作的改进

| 等级 | 标准 |
|------|------|
| ❌ 缺失 | 无分析环节 |
| ⚠️ 基础 | 人工回顾，无结构化输出 |
| ✅ 达标 | LLM 分析执行轨迹，输出结构化改进条目 |
| 🌟 优秀 | 区分"固化为工具调用" vs "记录为经验规避" vs "无需处理" |

**mirror-release Phase 14 的三分法是达标标准**：
- 固化为工具调用 → 确定性步骤，写入 SKILL.md Phase
- 记录为经验规避 → 条件性步骤，写入 Lessons Learned
- 无需处理 → 一次性问题，仅记录在报告中

### D4: 经验持久化 — 分析结果写到哪里、怎么管理

| 等级 | 标准 |
|------|------|
| ❌ 缺失 | 经验仅存在于对话上下文，用完即消失 |
| ⚠️ 基础 | 手动维护"注意事项"章节 |
| ✅ 达标 | 自动写入 Lessons Learned 章节，有去重 + FIFO 淘汰（上限 N 条） |
| 🌟 优秀 | 语义去重（embedding 相似度）+ LRU/引用频率淘汰 + 分类标签 |

**当前最佳实践**：
```python
def _merge_lessons(existing, new_items, max_entries=10):
    seen = {item.strip().lower() for item in existing}
    merged = list(existing)
    for item in new_items:
        if item.strip().lower() not in seen:
            merged.append(item)
    return merged[-max_entries:]  # FIFO 淘汰
```

### D5: 注入闭环 — 经验如何回到下次执行

| 等级 | 标准 |
|------|------|
| ❌ 缺失 | 经验写了但下次不读 |
| ⚠️ 基础 | 需要人工提醒 Agent 参考历史 |
| ✅ 达标 | Tier 2 加载时自动包含 Lessons Learned，Agent 自然读到 |
| 🌟 优秀 | 按当前任务上下文动态筛选最相关的经验注入 |

**核心验证**：执行路径上是否存在 `read SKILL.md → 执行 → 写 Lessons Learned → 下次 read 包含新内容` 的闭环。

### D6: 安全门禁 — 防止自迭代引入破坏

| 等级 | 标准 |
|------|------|
| ❌ 缺失 | Agent 可任意修改 SKILL.md，无审核 |
| ⚠️ 基础 | 依赖 git 版本控制兜底 |
| ✅ 达标 | 改进先写入 `.pending` 文件，需人工确认后合入 |
| 🌟 优秀 | 高置信度自动合入 + 低置信度人工审核 + prompt 注入检测 |

**prompt 注入检测（必须有）**：
```python
THREAT_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"you\s+are\s+now\s+",
    r"system\s+prompt\s*:",
    r"<\s*/?system\s*>",
    r"IMPORTANT:\s*NEW\s+INSTRUCTIONS",
    r"\u200b|\u200c|\u200d|\u200e|\u200f",  # 隐形 unicode
]
```

### D7: 可观测性 — 能追溯迭代历史

| 等级 | 标准 |
|------|------|
| ❌ 缺失 | 无法知道 SKILL.md 何时被改、为什么改 |
| ⚠️ 基础 | 依赖 git log |
| ✅ 达标 | 每次改进附带触发原因 + 执行 session_id + 时间戳 |
| 🌟 优秀 | 维护 `SKILL.md.versions.json` 变更日志，支持按条目回滚 |

## 评审流程

### Phase 1: 结构扫描

读取目标 SKILL.md，检查以下结构要素：

| 检查项 | 扫描方式 | 判定 |
|--------|----------|------|
| Lessons Learned 章节 | 正则 `##.*Lessons?\s+Learned|##.*经验|##.*已知问题` | 有/无 |
| 自检/回顾阶段 | 正则 `自检|retrospective|迭代|review|回顾` 出现在 Phase 定义中 | 有/无 |
| `.pending` 机制 | 检查 skill 目录下是否有 `.pending` 文件或代码中引用 `.pending` | 有/无 |
| references 目录 | 检查是否有 `references/` 子目录存放补充文档 | 有/无 |
| 版本追踪 | 检查 `.versions.json` 或 git log 中的 skill 变更记录 | 有/无 |

### Phase 2: 维度评分

逐一对照 D1-D7 评分，输出评分表：

```
📊 自迭代能力评审报告 — {skill_name}

| 维度 | 等级 | 说明 |
|------|------|------|
| D1 反馈采集 | ✅ | Phase 14 采集错误/耗时/阻塞 |
| D2 触发判定 | ⚠️ | 每次都执行，未区分"值得分析" |
| D3 分析能力 | ✅ | 三分法（固化/规避/忽略） |
| D4 经验持久化 | ⚠️ | 有 Lessons Learned 但无淘汰策略 |
| D5 注入闭环 | ✅ | Tier 2 加载自动包含 |
| D6 安全门禁 | ⚠️ | 依赖 git，无 .pending |
| D7 可观测性 | ⚠️ | 仅 git log |

总评：✅ 达标 3/7 | ⚠️ 基础 4/7 | ❌ 缺失 0/7
自迭代成熟度：L1（运行时自修复）已达标，L2（经验沉淀）部分达标
```

### Phase 3: 生成改进建议

针对每个非 ✅/🌟 的维度，输出具体、可操作的改进建议：

```
🔧 改进建议

1. [D2] 添加触发判定逻辑
   当前：Phase 14 每次都执行完整分析
   建议：在 Phase 14 开头增加快速判定——如果 Phase 0-13 全程无错误且轮数 < 35，
         输出"本次流程顺利"并跳过深度分析
   收益：减少约 60% 的无效分析轮数

2. [D4] 引入 FIFO 淘汰策略
   当前：Lessons Learned 只增不减
   建议：在 Phase 14.2 固化步骤中，当条目超过 10 条时淘汰最早的
   收益：防止 SKILL.md 膨胀超出 LLM 注意力窗口
```

## 配置

| 键 | 默认值 | 说明 |
|----|--------|------|
| MAX_LESSONS_ENTRIES | 10 | Lessons Learned 最大条目数 |
| TURNS_THRESHOLD | 20 | "成功但低效"的轮数阈值 |
| AUTO_MERGE_CONFIDENCE | 0.9 | 高于此置信度可跳过人工确认 |
| THREAT_SCAN_ENABLED | true | 是否启用 prompt 注入检测 |

## 边界与排除

以下场景不应触发本 skill，请 do not use skill-iter：

- 创建新 skill — 应由 yao-meta-skill 处理
- 代码重构 / bug 修复 — 不属于 skill 评审
- 知识问答（如"D1 维度是什么"）— 直接回答即可
- 工作流打包 — 应由 yao-meta-skill 处理
- 一次性脚本或迁移工具 — 不需要自迭代机制

触发词测试集见 `evals/trigger_cases.json`。

## 注意事项

- 评审结果是建议而非强制——不同 skill 的复杂度和执行频率不同，并非所有 skill 都需要 L3 能力
- 低频执行的 skill（如一次性迁移脚本）不需要经验沉淀机制
- 自迭代的核心价值是**降低人工干预频率**，而非追求零干预
- 改进建议必须考虑 token 成本——过度分析的 token 消耗可能超过收益

## 自检阶段 — Post-Execution Retrospective

每次评审执行完成后，Agent 必须执行以下自检流程：

**快捷方式（推荐）**：调用 `scripts/run_retrospective.py <skill_dir> --note "<备注>" --rating N --category <类别>` 一键执行完整管线。

**手动分步执行**：

1. **采集反馈**：调用 `scripts/collect_feedback.py` 记录本次执行的状态、轮数、错误情况
2. **触发判定**：调用 `scripts/should_improve.py` 判断是否值得启动深度分析
3. **轨迹分析**：调用 `scripts/analyze_trajectory.py` 对反馈执行三分法分类（固化/经验/忽略）
4. **安全扫描**：如果产生了新的经验条目，调用 `scripts/threat_scan.py` 扫描注入威胁
5. **经验暂存**：通过 `scripts/merge_lessons.py --add` 将改进建议写入 `.pending_lessons.json`
6. **人工确认**：提示用户执行 `scripts/merge_lessons.py --commit` 将 pending 经验合入 SKILL.md

注入闭环路径：`Agent 读取 SKILL.md（含 Lessons Learned）→ 执行评审 → 采集反馈 → 分析改进 → 写入 .pending → 人工确认合入 → 下次读取时自动包含`

## 工具链 — scripts/

| 脚本 | 功能 | D 维度 |
|------|------|--------|
| `collect_feedback.py` | 采集执行反馈到 `reports/feedback-log.json` | D1 |
| `should_improve.py` | 判定是否需要触发改进分析 | D2 |
| `analyze_trajectory.py` | 三分法分析（固化/经验/忽略），输出 `reports/analysis-report.json` | D3 |
| `merge_lessons.py` | 管理 Lessons Learned（.pending → 人工确认 → 合入） | D4, D6 |
| `threat_scan.py` | Prompt 注入检测 | D6 |
| `run_retrospective.py` | 端到端编排管线（collect→judge→analyze→scan→merge），输出 `reports/improvement-log.json` | D5, D7 |

## Lessons Learned

- 首次实现时发现 SKILL.md 仅定义标准但不满足自身标准，需 eat your own dog food
- D3（分析能力）仅有标准定义不够，必须配套 `analyze_trajectory.py` 实现三分法自动分类
- D5（注入闭环）依赖人工按序调用 4 个脚本不现实，需 `run_retrospective.py` 一键编排
- D7（可观测性）不能仅依赖 git log，`improvement-log.json` 记录触发原因/session/时间戳才可追溯
