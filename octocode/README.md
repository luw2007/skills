# Octocode Claude Code Skill

> ⚠️ **测试版本警告**
> 此 skill 目前处于**实验性测试阶段**，仅供学习和测试使用。
> **不建议在生产环境中使用**。功能和 API 可能会在未来版本中发生重大变化。

Claude Code skill，用于集成 Octocode AI 代码索引器的语义搜索、知识图谱和记忆系统功能。

## 什么是 Octocode?

Octocode 是一个基于 Rust 的 AI 代码索引工具，提供：
- **语义搜索**: 使用自然语言查询代码
- **知识图谱 (GraphRAG)**: AI 驱动的代码关系分析
- **记忆系统**: 持久化代码洞察和上下文
- **MCP 服务器**: Claude Desktop 集成

## 安装步骤

### 前置要求

1. **Claude Code CLI** - 已安装 Claude Code 命令行工具
2. **Octocode** - 已构建的 Octocode 项目

### 第一步：获取 Octocode

```bash
# 克隆 Octocode 仓库
git clone https://github.com/muvon/octocode.git
cd octocode

# 构建项目
cargo build --no-default-features --release
```

### 第二步：配置 Octocode

```bash
# 运行快速设置脚本
./scripts/setup.sh

# 或手动配置
mkdir -p ~/.config/octocode
cp config-templates/default-config.toml ~/.config/octocode/config.toml

# 设置 API Key（推荐 Voyage AI）
export VOYAGE_API_KEY="your-voyage-api-key"
```

**获取 API Key:**
- Voyage AI: https://www.voyageai.com (每月 200M 免费 tokens)
- OpenRouter: https://openrouter.ai/keys (可选，用于 LLM 功能)

### 第三步：安装 Skill

有两种安装方式：

#### 方式 1: 本地项目安装（推荐用于测试）

将 skill 复制到项目的 `.claude/skills/` 目录：

```bash
# 进入你的项目目录
cd /path/to/your/project

# 创建 skills 目录
mkdir -p .claude/skills

# 复制 skill
cp -r <path-to-skill-directory> .claude/skills/octocode
```

#### 方式 2: 全局安装

安装到 Claude Code 的全局 skills 目录：

```bash
# 查找 Claude Code 的 skills 目录
# macOS/Linux: ~/.claude/skills/
# Windows: %USERPROFILE%\.claude\skills\

# 复制 skill
cp -r <path-to-skill-directory> ~/.claude/skills/octocode
```

### 第四步：验证安装

在项目中启动 Claude Code 并测试 skill：

```bash
# 启动 Claude Code
claude

# 在 Claude Code 中询问
> 使用 octocode 搜索 "authentication logic"
> 用 octocode 分析这个项目的架构
> octocode 索引当前目录
```

Claude 会自动检测并使用 octocode skill 来处理相关请求。

## 使用示例

### 语义代码搜索

```
你: 使用 octocode 搜索用户认证相关的代码

Claude 会：
1. 检测到需要使用 octocode skill
2. 执行语义搜索命令
3. 返回相关代码片段和位置
```

### 知识图谱分析

```
你: 用 octocode 分析 src/auth 模块的依赖关系

Claude 会：
1. 使用 GraphRAG 功能
2. 分析模块间的关系
3. 展示依赖图和调用链
```

### 记忆系统

```
你: 用 octocode 记住：这个项目使用 JWT 进行认证，token 有效期为 24 小时

Claude 会：
1. 存储这个信息到 octocode 记忆系统
2. 在未来对话中可以检索这个上下文
```

## Skill 结构

```
claude-skill-octocode/
├── SKILL.md              # 主 skill 文件（包含 YAML frontmatter 和使用说明）
├── README.md             # 本文件（安装和使用指南）
├── scripts/              # 辅助脚本
│   ├── benchmark.sh      # 性能基准测试
│   ├── health-check.sh   # 健康检查
│   ├── setup.sh          # 快速设置
│   └── validate-config.sh # 配置验证
├── references/           # 参考文档
│   └── api-reference.md  # API 详细文档
└── assets/               # 资源文件（预留）
```

## 配置

### Octocode 配置

编辑 `~/.config/octocode/config.toml`:

```toml
[embedding]
model = "voyage-3:voyage-3"  # 推荐：Voyage AI

[search]
limit = 10
similarity_threshold = 0.7

[graphrag]
max_depth = 3
enable_llm_descriptions = true

[memory]
retention_days = 365
auto_git_tag = true
```

### 环境变量

在你的 shell 配置文件中添加：

```bash
# ~/.bashrc 或 ~/.zshrc
export VOYAGE_API_KEY="your-voyage-api-key"
export OPENROUTER_API_KEY="your-openrouter-key"  # 可选
```

## 故障排查

### Skill 未被识别

**症状**: Claude 说不知道 octocode

**解决方案**:
```bash
# 1. 检查 skill 位置
ls ~/.claude/skills/octocode/SKILL.md
# 或
ls .claude/skills/octocode/SKILL.md

# 2. 检查文件权限
chmod -R 755 ~/.claude/skills/octocode

# 3. 重启 Claude Code
```

### Octocode 命令失败

**症状**: Skill 运行但 octocode 命令报错

**解决方案**:
```bash
# 1. 验证 octocode 可执行
cd /path/to/octocode
cargo run -- --version

# 2. 运行健康检查
./scripts/health-check.sh

# 3. 检查 API keys
echo $VOYAGE_API_KEY
```

### 索引问题

**症状**: 搜索无结果

**解决方案**:
```bash
# 1. 重新索引
cd /path/to/your/project
cargo run --manifest-path /path/to/octocode/Cargo.toml -- index

# 2. 检查索引状态
ls -lh ~/.local/share/octocode/store/

# 3. 调试模式
RUST_LOG=debug cargo run --manifest-path /path/to/octocode/Cargo.toml -- search "test"
```

## 限制和已知问题

> ⚠️ **重要提醒**

### 当前限制

1. **实验性功能**: 此 skill 仍在积极开发中
2. **性能**: 大型代码库（>10万文件）可能需要优化
3. **准确性**: 语义搜索结果取决于嵌入模型质量
4. **API 依赖**: 需要外部 API keys（除非使用本地模型）

### 不推荐用于

- ❌ 生产环境的关键系统
- ❌ 处理敏感代码或专有代码（除非使用本地模型）
- ❌ 需要 100% 准确性的场景
- ❌ 实时性要求极高的应用

### 适合用于

- ✅ 个人学习和实验
- ✅ 开源项目探索
- ✅ 原型开发和概念验证
- ✅ 代码库理解和文档生成

## 更新 Skill

```bash
# 拉取最新 skill
cd <path-to-skill-directory>
git pull

# 更新到项目或全局目录
cp -r . ~/.claude/skills/octocode/
# 或
cp -r . /path/to/project/.claude/skills/octocode/
```

## 卸载

```bash
# 删除 skill
rm -rf ~/.claude/skills/octocode
# 或
rm -rf .claude/skills/octocode

# 可选：清理 octocode 数据
rm -rf ~/.local/share/octocode
rm -rf ~/.config/octocode
```

## 贡献

欢迎贡献！请查看：

- **Octocode 仓库**: https://github.com/muvon/octocode
- **Issue 追踪**: https://github.com/muvon/octocode/issues
- **讨论区**: https://github.com/muvon/octocode/discussions

## 许可证

### 许可证说明

| 项目 | 许可证 | 说明 |
|------|--------|------|
| **Octocode** | Apache-2.0 | 原始项目，由 Muvon Un Limited 开发 |
| **本 Skill** | MIT | 集成工具，由 luw2007 开发 |

### 协议兼容性

✅ **MIT 和 Apache 2.0 协议兼容**

本 Skill 使用 MIT 许可证是合法的，因为：

1. **不是派生作品**: 本 Skill 不包含 Octocode 的源代码，仅通过命令行接口调用
2. **独立作品**: 根据 Apache 2.0 定义，"仅链接到接口"的作品不算派生作品
3. **符合 Apache 2.0 要求**: 在 NOTICE 文件中提供了完整的归属声明

详见：
- **本项目许可**: [LICENSE](LICENSE) (MIT)
- **归属声明**: [NOTICE](NOTICE)
- **Octocode 许可**: https://github.com/muvon/octocode/blob/main/LICENSE (Apache-2.0)

### 商标声明

本项目不声明对 "Octocode" 或相关商标的任何权利。所有商标归其各自所有者所有。

## 相关链接

- **Octocode 主项目**: https://github.com/muvon/octocode
- **Claude Code 文档**: https://code.claude.com/docs
- **Claude Skills 指南**: https://github.com/anthropics/skills
- **Voyage AI**: https://www.voyageai.com
- **OpenRouter**: https://openrouter.ai

## 支持

如有问题或建议，请：

1. 查看 [API 参考文档](references/api-reference.md)
2. 运行健康检查: `./scripts/health-check.sh`
3. 在 GitHub 上创建 issue: https://github.com/muvon/octocode/issues

---

**免责声明**: 此 skill 处于实验性测试阶段。使用者需自行承担使用风险。不对任何因使用此 skill 造成的数据丢失、系统故障或其他问题负责。
