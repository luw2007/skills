---
name: octocode
description: AI-powered code indexer with semantic search, knowledge graphs (GraphRAG), and persistent memory system. Use when you need to (1) perform semantic code searches across large codebases, (2) analyze file relationships and dependencies through GraphRAG, (3) store and retrieve code insights with memory system. This skill uses Bash to call octocode CLI directly with automatic index management.
license: MIT
allowed-tools: ["bash", "read", "write", "glob", "grep"]
metadata:
  version: "0.2.0"
  category: "code-intelligence"
  requires: ["octocode-cli"]
  status: "experimental"
  warning: "仅供测试使用，不建议在生产环境中使用"
---

# Octocode - AI Code Intelligence Assistant

> ⚠️ **实验性测试版本警告**
>
> 此 skill 目前处于**早期实验阶段**（v0.2.0），功能和接口可能随时变化。
>
> **仅供学习和测试使用，不建议在生产环境中使用。**
>
> 使用风险自负。

Octocode 是一个基于 Rust 的 AI 代码索引工具，结合语义搜索、知识图谱（GraphRAG）和记忆系统能力。专为大型代码库设计，采用本地优先的方式。

**核心特性**：
- 🔍 **语义搜索**: 使用自然语言查询代码
- 🕸️ **知识图谱 (GraphRAG)**: AI 驱动的代码关系分析
- 💾 **记忆系统**: 持久化代码洞察和上下文
- 🤖 **自动索引管理**: 自动检测并提示创建索引，无需手动操作

**实现方式**：
- 本 skill 通过 **Bash 直接调用 `octocode` CLI**
- 自动检测索引状态，首次使用时提示用户创建
- 支持实时显示索引创建进度
- 详细使用指南请参考：[README.md](README.md)

---

## 🎯 核心工作流集成

> **说明**：本 skill 整合了 `~/.claude/CLAUDE.md` 中定义的多模型协作工作流（Phase 1: 上下文检索，Phase 6: 知识结晶）。完整工作流协议请参考该全局配置文件。

### Phase 1: 上下文全量检索 (Context Acquisition)

**执行原则**：优先使用语义检索获取全面上下文。

#### 工具选择优先级

1. **Octocode (首选)**: 语义搜索 + GraphRAG 知识图谱 (通过 Bash 调用 CLI)
   - 自动索引检测：使用前自动检查索引状态
   - `octocode search "<query>"`: 语义级代码搜索
   - `octocode graphrag <operation>`: 关系图谱查询（文件依赖、调用链、架构理解）
   - `octocode view <files>`: 快速浏览文件签名结构

2. **Fallback**: 当 Octocode 未安装或无法使用时 → `glob` + `grep` + 手动验证

#### 检索策略

- **禁止基于假设（Assumption）回答**
- 使用自然语言（NL）构建语义查询（Where/What/How）
- **完整性检查**：必须获取相关类、函数、变量的完整定义与签名。若上下文不足，触发递归检索
- **整体检索策略**：
  1. **首次使用自动检测**：执行搜索前，自动运行 `scripts/check_index.sh` 检查索引状态
  2. **无索引时提示**：若检测到无索引，使用 `AskUserQuestion` 询问用户是否创建
  3. **用户同意后创建**：运行 `octocode index` 异步创建索引，实时显示进度
  4. **索引就绪后搜索**：索引创建完成后，执行语义搜索
  5. **精确定位**：使用 `glob`/`grep` 做精确定位与兜底确认

#### 强制要求

```
✅ Phase 1 必须先用 octocode search 或 octocode graphrag 检索
✅ 首次使用时必须检查索引状态 (运行 scripts/check_index.sh)
✅ 无索引时必须提示用户创建 (使用 AskUserQuestion)
✅ 一次性获取符号、依赖、调用链
✅ 上下文不足必须追溯
❌ 禁止 grep / keyword search 作为首选
❌ 禁止基于假设或内部知识回答
❌ 禁止未获取完整上下文就开始编码
❌ 禁止跳过索引检测直接搜索
```

#### 最佳实践

- **自动索引检测**：每次搜索前自动运行 `bash scripts/check_index.sh`
- **用户确认创建**：无索引时使用 `AskUserQuestion` 询问用户
- **搜索流程**：先用 `octocode search` 获取全局视图，再用 `glob`/`grep` 精确定位
- **依赖追踪**：若上下文不足，使用 `octocode graphrag` 追踪依赖关系
- 检索到的信息应包含完整的函数签名、类定义和导入关系

#### 索引检测脚本示例

```bash
# 检查当前项目是否有索引
SKILL_DIR="${HOME}/.claude/skills/octocode"
if ! bash "${SKILL_DIR}/scripts/check_index.sh"; then
    # 使用 AskUserQuestion 询问用户是否创建索引
    # 如果用户同意，运行: octocode index
fi
```

---

### Phase 6: 知识结晶 (Knowledge Crystallization)

**执行者**：Claude Code
**执行条件**：交付成功后

#### 记忆存储策略

若任务涉及特定的**用户偏好**或**项目隐式约定**（非显式写在文档中的），使用 `octocode memory save` 命令记录。

**⚠️ 安全警告**：
- **禁止**存储密钥、API tokens、密码等敏感信息
- **禁止**存储 PII（个人身份信息）
- 仅记录技术决策、架构约定、Bug 修复上下文

**使用示例**（通过 Bash）：
```bash
# 记录技术决策
octocode memory save "Fixed race condition in token refresh logic by adding mutex lock" \
  --type bug_fix \
  --tags security,jwt,race-condition \
  --files src/auth/jwt.rs,src/middleware/auth.rs
```

#### 记忆类型

- `code`: 代码相关
- `architecture`: 架构决策
- `bug_fix`: Bug 修复
- `optimization`: 性能优化
- `security`: 安全相关
- `testing`: 测试相关
- `documentation`: 文档

---

## 🛠️ Octocode CLI 命令详解

> **说明**: 本 skill 通过 Bash 直接调用 `octocode` CLI 命令，自动处理索引检测和创建。

### 1. search - 语义搜索

**用途**：语义级代码搜索，支持自然语言查询

**自动化特性**：
- ✅ 使用前自动检测索引状态（通过 `scripts/check_index.sh`）
- ✅ 无索引时提示用户创建（使用 `AskUserQuestion`）
- ✅ 异步创建索引，实时显示进度

**CLI 命令**：
```bash
# 基本语义搜索（自动处理索引）
octocode search "authentication logic"

# 搜索特定概念
octocode search "HTTP request handling with error recovery"

# 搜索代码模式
octocode search "database connection pooling implementation"

# 高级选项
octocode search "API endpoints" --mode code --expand
```

**使用场景**：
- 理解陌生代码库的架构和组织
- 查找特定功能的实现位置
- 发现代码中的相关模式和用法
- 跨文件追踪功能流程

---

### 2. graphrag - 知识图谱

**用途**：基于关系的代码架构分析

**自动化特性**：
- ✅ 自动检测索引状态
- ✅ 无索引时提示创建

**操作类型**：
- `search` - 语义搜索节点
- `get-node` - 获取节点详细信息
- `get-relationships` - 查看节点关系
- `find-path` - 查找节点间路径
- `overview` - 图谱统计概览

**CLI 命令**：
```bash
# 语义搜索关系
octocode graphrag search --query "How does user authentication flow through the system?"

# 获取节点详情
octocode graphrag get-node --node-id src/auth/mod.rs

# 查看节点关系
octocode graphrag get-relationships --node-id src/auth/mod.rs

# 查找依赖路径
octocode graphrag find-path --source-id src/auth/mod.rs --target-id src/database/mod.rs

# 图谱概览
octocode graphrag overview
```

**关系类型**：
- `imports`: 直接依赖关系
- `sibling_module`: 同目录文件
- `parent_module` / `child_module`: 层级结构

**使用场景**：
- 理解模块间的依赖关系
- 追踪功能的调用链
- 分析代码架构和组织结构
- 识别潜在的循环依赖

---

### 3. view - 查看文件签名

**用途**：快速提取文件的函数签名、类定义等结构

**CLI 命令**：
```bash
# 查看特定文件
octocode view src/main.rs src/lib.rs

# 使用 glob 模式
octocode view "src/**/*.rs"

# 多语言分析
octocode view "**/*.{rs,py,js,ts}"
```

---

### 4. memory - 记忆系统

#### save - 存储记忆

**CLI 命令**：
```bash
# 存储记忆
octocode memory save "Fixed race condition in JWT token refresh" \
  --type bug_fix \
  --tags security,jwt,race-condition \
  --files src/auth/jwt.rs

# 简单记录
octocode memory save "Refactored authentication module for better testability"
```

#### search - 检索记忆

**CLI 命令**：
```bash
# 搜索记忆
octocode memory search "authentication issues"

# 列出所有记忆
octocode memory list
```

#### forget - 删除记忆

**CLI 命令**：
```bash
# 删除特定记忆
octocode memory forget <memory-id>
```

---

## 📋 工作流示例

### 场景 1：探索新代码库（遵循 Phase 1 协议）

```bash
# 1. Phase 1: 语义搜索理解架构（自动处理索引）
octocode search "main entry point and initialization"
octocode search "configuration and settings management"
octocode search "database access patterns"

# 2. 使用 GraphRAG 理解依赖
octocode graphrag overview
octocode graphrag search --query "How is the database connected?"

# 3. Phase 6: 保存发现（知识结晶）
octocode memory save "Main entry in src/main.rs, uses config from config/"
```

### 场景 2：调试和修复 Bug（完整工作流）

```bash
# Phase 1: 搜索相关代码（自动处理索引）
octocode search "authentication token validation"

# Phase 1: 分析依赖关系
octocode graphrag get-relationships --node-id src/auth/token.rs

# Phase 1: 查找类似的 Bug 修复（记忆检索）
octocode memory search "token validation bugs"

# Phase 2-5: 由 Claude Code 协调多模型完成

# Phase 6: 修复后记录（知识结晶）
octocode memory save "Fixed token expiry check in validate_token()" \
  --type bug_fix \
  --tags security,authentication
```

### 场景 3：在 Claude Code 中使用（推荐工作流）

```bash
# Step 1: 检查索引状态
if ! bash ~/.claude/skills/octocode/scripts/check_index.sh; then
    # Step 2: 使用 AskUserQuestion 询问用户
    # 问题: "当前项目尚未创建 octocode 索引，是否现在创建?"
    # 选项: ["是，创建索引 (推荐)", "否，跳过"]

    # Step 3: 如果用户同意，创建索引
    octocode index
fi

# Step 4: 执行搜索
octocode search "functions that call gemini-3-flash model"
```

---

## 🎯 最佳实践（遵循 CLAUDE.md 原则）

### Phase 1 检索策略

- ✅ **强制使用** Octocode 语义检索（search + graphrag）
- ✅ **自动索引检测**：每次搜索前运行 `scripts/check_index.sh`
- ✅ **用户确认创建**：无索引时使用 `AskUserQuestion` 询问
- ✅ 使用自然语言描述性查询
- ✅ 完整性检查，上下文不足时递归检索
- ✅ 先 search 获取全貌，再 glob/grep 精确定位
- ❌ **禁止**基于假设回答
- ❌ **禁止** grep/keyword 作为首选
- ❌ **禁止**未获取完整上下文就编码
- ❌ **禁止**跳过索引检测直接搜索

### Phase 6 记忆管理

- ✅ 记录重要的技术决策和隐式约定
- ✅ 使用标签组织记忆
- ✅ 关联相关文件路径
- ❌ 不要存储临时或过时的信息
- ❌ 不要存储敏感信息（密钥、密码等）

### 索引管理

- ✅ **首次使用自动提示**：skill 自动检测并提示创建
- ✅ 在大型变更后重新索引（运行 `octocode index`）
- ✅ 使用 watch 模式进行活跃开发（`octocode watch`）
- ❌ 不要在 CI/CD 中频繁重建索引

---

## 🚫 反模式速查（Anti-Patterns）

### ❌ 致命错误（立即纠正）

1. **Phase 1 未使用 Octocode 语义检索** → 浪费 Token，信息不完整
2. **跳过索引检测直接搜索** → 可能返回空结果
3. **基于假设或内部知识回答** → 违反检索强制原则
4. **跳过完整性检查直接编码** → 上下文缺失导致错误
5. **未使用记忆系统沉淀知识** → 无法积累项目上下文
6. **在记忆中存储密钥/PII** → 安全风险，禁止存储敏感信息

### ✅ 强制执行（不可违背）

1. **Octocode 优先**：Phase 1 **必须**先用 `octocode search` 或 `octocode graphrag` 检索
2. **自动索引检测**：**必须**在搜索前运行 `scripts/check_index.sh`
3. **用户确认创建**：无索引时**必须**使用 `AskUserQuestion` 询问
4. **完整查询**：一次性获取符号、依赖、调用链
5. **递归检索**：上下文不足**必须**追溯
6. **知识结晶**：任务结束后用 `octocode memory save` 沉淀偏好
7. **禁止假设**：**绝对禁止**基于假设或内部知识回答

---

## 🔧 基本配置

### 前置要求

1. **Octocode CLI**: 确保 `octocode` 命令已安装并在 PATH 中可用
2. **API Keys**: 配置至少一个 Embedding 模型的 API key

### 环境变量

```bash
# Embedding 模型（至少需要一个）
export VOYAGE_API_KEY="..."       # 推荐，每月 200M 免费 tokens
# export JINA_API_KEY="..."       # 或 Jina AI
# export GOOGLE_API_KEY="..."     # 或 Google

# 可选：LLM 功能（用于 CLI commit/review）
export OPENROUTER_API_KEY="..."
```

### 项目索引

**无需手动操作！** 本 skill 实现了自动索引管理：

1. **首次使用时自动检测**：执行搜索前，自动运行 `scripts/check_index.sh` 检查索引状态
2. **智能提示用户**：若检测到无索引，使用 `AskUserQuestion` 询问用户是否创建
3. **异步创建索引**：用户确认后，运行 `octocode index` 创建索引并实时显示进度
4. **索引就绪后搜索**：索引创建完成后，自动继续执行搜索操作

**手动索引（可选）**：

```bash
# 如果想提前创建索引
cd /path/to/your/project
octocode index

# 监控模式（自动增量更新）
octocode watch
```

### 索引检测脚本

skill 包含一个辅助脚本用于检测索引状态：

```bash
# 位置
~/.claude/skills/octocode/scripts/check_index.sh

# 使用
if ! bash ~/.claude/skills/octocode/scripts/check_index.sh; then
    echo "需要创建索引"
fi
```

---

## 📚 更多资源

- **完整文档**: [README.md](README.md) - 项目说明和安装指南
- **API 参考**: [references/api-reference.md](references/api-reference.md) - CLI 命令完整参考
- **快速开始**: [QUICKSTART.md](QUICKSTART.md) - 快速入门教程
- **项目仓库**: [octocode](https://github.com/muvon/octocode) - octocode 主项目

---

> ⚠️ **再次提醒**: 此项目仍在活跃开发中（v0.2.0），功能和 API 可能随时变化。生产环境请谨慎使用。
