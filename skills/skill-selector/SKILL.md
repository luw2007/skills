---
name: skill-selector
description: 通用 skill 选择器。通过 ai-skills CLI 下载候选 skill 源码到临时目录，基于 SKILL.md + 代码的深度分析构建决策树，引导用户在 1-3 轮交互内选定最合适的 skill。当用户面对多个功能相近的 skill 不知选哪个时触发。
---

<!-- 兼容性: Claude Code / Trae Solo / Agent Skills 标准 -->
<!-- 仅在 frontmatter 中使用 `name` 和 `description` 以保持最大兼容性 -->

# Skill Selector

通过 5 步流程引导用户选定最合适的 skill：获取候选源码 → 深度提取 → 动态维度推导 → 交互式收窄 → 对比矩阵推荐。

与仅依赖搜索结果简述的"简版决策树"不同，本流程将候选 skill 下载到临时目录后，基于 SKILL.md 全文 + 代码实现 + 配置文件进行深度分析，确保对比矩阵的每一项都有源码级可追溯依据。

## 输入

用户提供 skill 候选列表，支持以下格式：

- **搜索关键词**：如 `argos`，通过 `ai-skills find` 搜索并筛选候选
- **skill 名称列表**：如 `argos-log, argos-query`，直接作为候选
- **安装命令列表**：如 `ai-skills add anthropics/skills --source github --skill skill-creator`，直接解析执行
- **路径列表**：直接指向已有的 SKILL.md 所在目录或文件（跳过下载）
- **结构化对象**：包含 name 和 install_cmd 的 JSON 数组

## 核心流程

```
输入: skill 候选（关键词 / 名称 / 安装命令 / 路径）
    │
    ▼
Step 0: 获取候选源码 → 临时目录
    │  ai-skills find（搜索）→ ai-skills add --dir（下载）
    ▼
Step 1: 深度提取 → 结构化摘要（SKILL.md + 代码 + 配置）
    │
    ▼
Step 2: 预构建完整决策树（含叶节点对比矩阵）
    │
    ▼
Step 3: 沿决策树交互 → 用户选择即时下探，命中已有分支零延迟
    │
    ▼
Step 4: 到达叶节点 → 输出预计算的对比矩阵 + 推荐
    │
    ▼
清理: 删除临时目录
```

**关键设计原则**：Step 0 + Step 1 一次性完成下载和分析。Step 2 一次性完成决策树构建。Step 3 不做任何新的分析，只是沿预构建的树遍历。用户每次选择后应**立即**呈现下一层选项或最终结果，无需等待额外计算。

---

## Step 0: 获取候选源码

### 0.1 搜索候选

当输入为搜索关键词时，执行：

```bash
ai-skills find <关键词> --pure
```

解析输出，提取每个命中结果的：
- skill 名称（如 `argos-log`）
- 版本（如 `v0.2.0`）
- 下载量
- 简述（用于初筛，不作为最终分析依据）
- 安装命令（如 `ai-skills add liuweiming/skills --skill argos-log --source local --pure`）

如有多页结果（输出末尾含 `Next: ai-skills find ... --page N`），继续翻页直到收集完毕。

### 0.2 初筛

在下载前进行轻量初筛，排除明显不相关的候选：
- 对比 skill 简述与用户需求关键词的语义相关度
- 用户明确指定的 skill 名称列表不做初筛，全部保留
- 初筛结果告知用户，展示保留和排除的 skill 及原因

### 0.3 下载到临时目录

为本次分析创建临时目录，将所有候选 skill 下载到其中：

```bash
tmpdir=$(mktemp -d -t skill-selector-XXXXXX)
ai-skills add <repo> --skill <name> --source local --dir "$tmpdir" --pure --yes
```

每个 skill 下载后在临时目录中的结构：

```
$tmpdir/
├── argos-log/
│   ├── SKILL.md
│   ├── assets/
│   │   └── config.json
│   └── references/
│       └── ...
├── argos-query/
│   ├── SKILL.md
│   └── ...
└── ...
```

### 0.4 下载失败处理

- 单个 skill 下载失败 → 标记为「⚠️ 下载失败」，继续处理其余候选
- 全部下载失败 → 告知用户检查网络或 ai-skills 登录状态（`ai-skills login`）
- 下载超时 → 跳过该 skill，标记原因

### 0.5 本地路径输入

当输入已是路径列表时，跳过 Step 0 的搜索和下载步骤，直接使用指定路径进入 Step 1。

---

## Step 1: 深度提取

### 1.1 读取策略

对临时目录中的每个候选 skill，按以下顺序读取并分析：

1. **SKILL.md**（必读）→ 技能描述、触发条件、使用方式的权威来源
2. **代码文件**（深度分析）→ 遍历 skill 目录中的所有代码文件（`.sh`、`.py`、`.js`、`.ts` 等），提取：
   - 实际调用的外部命令和工具链（如 `bytedcli`、`gdpa-cli`、`argos`）
   - 依赖的环境变量和配置项
   - 核心逻辑流程和分支条件
   - 错误处理策略
3. **配置文件**（辅助分析）→ 读取 `assets/`、`references/`、`config.*` 等目录/文件：
   - 默认参数和可配置项
   - 支持的选项枚举
4. **package.json / requirements.txt 等**（如存在）→ 外部依赖列表

### 1.2 结构化摘要 Schema

对每个候选 skill 的全部内容，提取以下结构化摘要：

```json
{
  "name": "skill 名称（取 frontmatter name 字段）",
  "version": "版本号",
  "one_liner": "一句话说明（≤30 字）",
  "domain": "所属领域（如 SRE、前端开发、数据库、DevOps、测试…）",
  "capabilities": [
    "能力描述 1（动词开头）",
    "能力描述 2",
    "能力描述 3"
  ],
  "prerequisites": [
    "前置条件（安装/配置/权限），没有则为空数组"
  ],
  "trigger_patterns": ["触发词 1", "触发词 2"],
  "input_format": "接受的输入格式",
  "output_format": "输出格式",
  "unique_strengths": ["独有优势 1"],
  "known_limitations": ["已知限制 1"],
  "implementation": {
    "external_tools": ["实际调用的外部命令列表（从代码中提取）"],
    "env_vars": ["依赖的环境变量"],
    "core_logic": "核心逻辑概述（从代码中提取的实际流程）",
    "file_count": "skill 包含的文件数量",
    "code_quality_signals": ["代码质量信号：有无错误处理、日志、重试等"]
  }
}
```

### 1.3 提取指令

对每个候选 skill 目录执行以下分析：

```
给定以下 skill 的完整内容（SKILL.md + 代码文件 + 配置文件），提取结构化摘要。
字段定义：
- name: skill 名称（取 frontmatter name 字段）
- version: 版本号（取 frontmatter 或搜索结果）
- one_liner: 一句话说明这个 skill 做什么（不超过 30 字）
- domain: 所属领域（如 SRE、前端开发、数据库、DevOps、测试…）
- capabilities: 该 skill 能做什么（3-5 条，动词开头）
- prerequisites: 使用前需要什么（安装、配置、权限等，没有则为空数组）
- trigger_patterns: 什么样的用户输入应该触发这个 skill
- input_format: 接受什么格式的输入
- output_format: 输出什么格式的结果
- unique_strengths: 相比同类 skill 的独有优势
- known_limitations: 已知限制
- implementation.external_tools: 代码中实际调用的外部命令（grep 代码提取，非猜测）
- implementation.env_vars: 代码中引用的环境变量
- implementation.core_logic: 从代码中提取的实际执行流程（不是 SKILL.md 描述，是代码实现）
- implementation.file_count: 文件数量
- implementation.code_quality_signals: 代码质量信号
输出纯 JSON，不要解释。
```

### 1.4 缓存策略

- 以 skill 目录内所有文件的综合 hash 作为缓存 key
- 同一会话内遇到相同 hash 的 skill，直接复用已有摘要，不重复分析
- 无持久化缓存（每次新会话重新分析，保证使用最新内容）

---

## Step 2: 预构建完整决策树

拿到所有候选的结构化摘要后，**一次性**完成维度分析、决策树构建和叶节点对比矩阵预计算。此步骤结束后，后续交互所需的全部数据均已就绪。

### 2.1 候选维度池（参考，非硬编码）

| 维度 | 来源字段 | 示例 |
|------|----------|------|
| 领域/场景 | domain, capabilities | SRE / 前端 / 数据库 |
| 覆盖范围 | one_liner, capabilities | 国内 / 海外 / 全量 |
| 操作粒度 | capabilities | 原始查询 / 诊断分析 / 配置管理 |
| 前置成本 | prerequisites | 零配置 / 需 CLI / 需登录 |
| 工具链 | prerequisites, input_format | byte-cli / argos cli / curl |
| 输出形式 | output_format | 文本 / JSON / 自动存文件 |

维度从摘要中动态推导，上表仅为参考。LLM 应根据实际摘要内容识别最有区分力的维度。

### 2.2 维度排序

按**区分力**排序：优先选择能把候选集切分为最均匀子集的维度。

评估标准：
- 该维度下各分支候选数量越均匀，区分力越强
- 该维度下只有 1 个分支（所有候选相同）→ 区分力为零，跳过

### 2.3 完整决策树构建

递归构建**完整决策树**，包含所有分支路径直到叶节点：

1. 选择当前区分力最强的维度
2. 按该维度的取值切分候选集
3. 对每个子集递归，直到叶节点 ≤ 3 个候选
4. **叶节点预计算对比矩阵和推荐结果**（见 2.5 节）

### 2.4 决策树 Schema

构建的决策树必须符合以下结构，在后续交互中直接引用：

```json
{
  "type": "decision",
  "dimension": "场景",
  "question": "你的主要需求是？",
  "branches": {
    "日志查询": {
      "skills": ["argos-log", "argos-query", "argos-tools", "argos-log-i18n", "bytedance-log-i18n"],
      "child": {
        "type": "decision",
        "dimension": "区域",
        "question": "你需要查询哪个区域的日志？",
        "branches": {
          "国内": {
            "skills": ["argos-log", "argos-query", "argos-tools"],
            "child": {
              "type": "leaf",
              "skills": ["argos-log", "argos-query", "argos-tools"],
              "comparison_matrix": { "...预计算的对比矩阵..." : "..." },
              "recommendation": { "pick": "argos-tools", "reason": "..." }
            }
          },
          "海外": {
            "skills": ["argos-log-i18n", "bytedance-log-i18n"],
            "child": {
              "type": "leaf",
              "skills": ["argos-log-i18n", "bytedance-log-i18n"],
              "comparison_matrix": { "...预计算的对比矩阵..." : "..." },
              "recommendation": { "pick": "argos-log-i18n", "reason": "..." }
            }
          }
        }
      }
    },
    "综合诊断": {
      "skills": ["argos"],
      "child": {
        "type": "leaf",
        "skills": ["argos"],
        "recommendation": { "pick": "argos", "reason": "唯一候选" }
      }
    }
  }
}
```

节点类型：
- **decision**：内部节点，包含 dimension（维度）、question（提问文案）、branches（各分支及对应子节点）
- **leaf**：叶节点，候选 ≤ 3 个，包含预计算的 comparison_matrix 和 recommendation

### 2.5 叶节点预计算

每个叶节点在构建时就完成以下预计算：

**当候选 = 1 个**：
- 直接记录该 skill 的推荐和使用方法概要

**当候选 = 2~3 个**：
- 预计算对比矩阵（只展示有差异的维度）
- 预计算推荐结果 + 推荐理由（2-3 句话）
- 预计算使用方法概要

### 2.6 构建约束

- 每个 decision 节点的分支数 ≤ 4（AskUserQuestion 工具限制）
- 分支超过 4 个时，合并最相似的分支
- 树深度最多 3 层（对应最多 3 轮交互）
- 3 层后仍 > 3 个候选的子集，取前 3 个构建叶节点

---

## Step 3: 沿决策树交互

### 3.1 核心原则

**零延迟下探**：用户每次选择后，直接读取预构建决策树中对应分支的子节点，立即呈现下一层选项或最终结果。不做任何新的分析或计算。

### 3.2 遍历规则

从决策树根节点开始：

1. **当前节点为 decision** → 用 AskUserQuestion 呈现该节点的 question 和 branches 的 key 列表
2. **用户选择某分支** → 跳转到 `branches[选择].child`
3. **跳转后的节点为 decision** → 重复步骤 1（立即呈现，不重新分析）
4. **跳转后的节点为 leaf** → 直接输出预计算的对比矩阵和推荐（见 Step 4）
5. **某分支只有 1 个 skill** → 自动跳过该层，直接输出该 skill 的推荐和使用方法

### 3.3 自动跳过规则

- 当某 decision 节点只有 1 个分支 → 自动跳过，直接进入唯一分支的 child
- 当分支内只有 1 个 skill → 直接输出推荐，无需进入对比矩阵

### 3.4 交互格式

每轮交互需要告知用户：
1. 当前剩余候选数量
2. 本轮的区分维度和各选项含义
3. 每个选项对应的候选 skill 数量

---

## Step 4: 输出预计算结果

### 4.1 触发条件

到达叶节点（候选 ≤ 3 个）时触发，直接输出 Step 2 中预计算的结果。

### 4.2 矩阵格式（2~3 个候选）

```markdown
| 维度 | skill-A | skill-B | skill-C |
|------|---------|---------|---------|
| 定位 | ... | ... | ... |
| 独有能力 | ✅ X | ❌ X | ✅ X |
| 前置条件 | 需 argos cli | 需 byte-cli | 零依赖 |
| 输出方式 | JSON | 自动存文件 | 文本 |
| 亮点 | ... | ... | ... |
| 限制 | ... | ... | ... |
```

### 4.3 输出规则

1. **只展示有差异的维度**（所有候选相同的项不列出）
2. 矩阵末尾给出**明确推荐** + **推荐理由**（2-3 句话）
3. 用户确认选定后，输出该 skill 的**使用方法概要**：
   - 安装/配置步骤（如有）
   - 典型调用方式
   - 关键注意事项

---

## 边界处理

| 情况 | 处理 |
|------|------|
| 输入为空 | 提示用户提供 skill 候选列表或搜索关键词 |
| `ai-skills` CLI 未安装 | 提示用户执行 `npm i -g @tiktok-fe/skills` 安装 |
| 搜索无结果 | 告知用户换关键词重试，或直接提供 skill 路径 |
| 单个 skill 下载失败 | 标记为「⚠️ 下载失败」，继续处理其余候选 |
| 全部下载失败 | 告知用户检查 `ai-skills login` 登录状态和网络 |
| skill 目录中无 SKILL.md | 标记为「⚠️ 缺少 SKILL.md」，尝试从目录中其他文件推断能力 |
| 只有 1 个有效候选 | 直接输出该 skill 的深度摘要和使用方法，跳过交互 |
| 所有候选完全相同 | 告知用户这些 skill 功能等价，任选一个即可 |
| 候选 > 15 个 | 警告下载和分析耗时较长，建议先通过初筛缩小范围 |
| 有效候选经过跳过后为 0 | 告知用户所有候选均无法分析，检查关键词或路径 |

## 临时目录生命周期

- **创建时机**：Step 0.3，在开始下载前创建
- **使用范围**：Step 0（下载）和 Step 1（读取分析）
- **清理时机**：Step 1 完成后（所有摘要已提取到内存），立即执行 `rm -rf "$tmpdir"`
- **异常清理**：如果流程中断，临时目录位于系统 tmp 目录（`/tmp/skill-selector-*`），由操作系统定期清理

---

## 交互示例

以下展示一个从搜索关键词出发，经过下载、深度分析、决策树交互，最终选定 1 个 skill 的完整流程。

### 输入

```
请帮我选一个查 argos 日志的 skill
```

### Step 0: 获取候选源码

```
🔍 搜索: ai-skills find argos --pure
   命中 10 个结果（2 页），翻页收集完毕。

📋 初筛结果（排除明显不相关）：
   ✅ 保留 8 个: argos-log, argos, argos-log-i18n, argos-query, argos-tools,
                 bytedance-log-i18n, bytedance-apm, modify-argos-alarm-rule
   ❌ 排除 2 个: dh-ops-debug-job-failure（DH 任务调试，与日志查询无关）
                 hornbill-dev（工单平台开发，与 argos 无关）

📦 下载到临时目录: /tmp/skill-selector-a1b2c3/
   ✅ argos-log (2 files)
   ✅ argos (1 file)
   ✅ argos-log-i18n (3 files)
   ✅ argos-query (1 file)
   ✅ argos-tools (1 file)
   ✅ bytedance-log-i18n (4 files)
   ✅ bytedance-apm (2 files)
   ✅ modify-argos-alarm-rule (2 files)
```

### Step 0 + Step 1 + Step 2 输出（首次响应，一次性完成）

```
✅ 下载并深度分析了 8 个候选 skill（SKILL.md + 代码 + 配置）。
✅ 决策树构建完成（2 层深度，覆盖全部 8 个候选的所有路径）。
🧹 临时目录已清理。

决策树概览：
├── 日志查询 (5)
│   ├── 国内 (3) → [argos-log, argos-query, argos-tools] → 对比矩阵已就绪
│   └── 海外 (2) → [argos-log-i18n, bytedance-log-i18n] → 对比矩阵已就绪
├── 综合诊断 (1) → argos → 直接推荐
├── 指标监控 (1) → bytedance-apm → 直接推荐
└── 报警管理 (1) → modify-argos-alarm-rule → 直接推荐

→ AskUserQuestion: 你的主要需求是？
  选项: 日志查询(5) / 综合诊断(1) / 指标监控(1) / 报警管理(1)
```

### 用户选择：日志查询 → 即时下探（零延迟）

```
日志查询类 5 个 skill，按区域分为：

→ AskUserQuestion: 你需要查询哪个区域的日志？
  选项: 国内(3) / 海外(2)
```

### 用户选择：国内 → 到达叶节点，直接输出预计算结果

```
| 维度 | argos-log | argos-query | argos-tools |
|------|-----------|-------------|-------------|
| 定位 | byte-cli 日志查询 | gdpa-cli 日志查询 | argos CLI 日志工具 |
| 工具链（代码验证） | bytedcli log | gdpa-cli argos-query | argos log.* 子命令 |
| 查询模式 | TraceQuery + KeywordQuery | Keyword + LocalFile + LogID | log.* 子命令 |
| 前置条件 | 需安装 byte-cli + 浏览器登录态 | 需安装 gdpa-cli | 需安装 argos CLI + 扫码登录 |
| 输出方式 | JSON（需 output-filter） | 结构化 JSON | 文本（大输出自动存文件） |
| 独有优势 | 精确 KV 过滤、分页 | 三种模式自动切换、PPE 支持 | 自动保存大输出、简洁命令 |
| 代码质量 | ✅ 错误处理完善 | ✅ 多模式分支清晰 | ⚠️ 较简单 |

**推荐: argos-tools**
理由: 命令最简洁，自动处理大输出，适合日常快速查询。如果需要精确过滤条件用 argos-log，需要 PPE 本地日志用 argos-query。
（以上对比基于源码级分析，非简述推断）
```

### 交互对比：如果用户选择了"综合诊断"

因为该分支只有 1 个 skill（argos），直接输出推荐，无需进入对比矩阵：

```
综合诊断类只有 1 个候选: argos

**推荐: argos**
使用方法: 直接描述服务问题，argos 会自动进行多维度诊断分析...
```
