# skills

A collection of AI Agent Skills.

## Available Skills

| Skill | Description |
|-------|-------------|
| [cli-help-layers](./skills/cli-help-layers/) | CLI 帮助信息分层设计指南，让 AI Agent 高效解析和调用 CLI 命令 |
| [favorites-curator](./skills/favorites-curator/) | 从本地已安装的仓库、应用、skill、扩展中构建和维护收藏目录清单 |
| [langextract-search](./skills/langextract-search/) | 集成智谱搜索、DuckDuckGo 搜索和多模型结构化提取的完整工作流 |
| [metadata-naming](./skills/metadata-naming/) | 定义、应用或审查基于元数据的可复用文件命名规范 |
| [octocode](./skills/octocode/) | AI 驱动的代码索引器，提供语义搜索、知识图谱（GraphRAG）和持久化记忆系统 |
| [rtk-rewrite](./skills/rtk-rewrite/) | 拦截 exec 工具调用并委托 rtk rewrite 执行重写以减少 token 消耗 |
| [skill-iter](./skills/skill-iter/) | Skill 自迭代能力评审与改进工具，输出结构化评分报告与改进建议 |
| [skill-selector](./skills/skill-selector/) | 通用 skill 选择器，通过深度分析构建决策树，引导用户快速选定最合适的 skill |
| [skill-yao-manager](./skills/skill-yao-manager/) | Skill 工程化管理工具，支持创建、验证、检查、lint、打包 skill |

## Installation

### Via npx skills (Recommended)

```bash
# 列出可用 skill
npx skills add luw2007/skills --list

# 安装指定 skill
npx skills add luw2007/skills --skill cli-help-layers
npx skills add luw2007/skills --skill octocode
npx skills add luw2007/skills --skill skill-selector

# 安装全部
npx skills add luw2007/skills --all
```

### Manual

```bash
git clone https://github.com/luw2007/skills.git
cp -r skills/skills/octocode ~/.claude/skills/
cp -r skills/skills/skill-selector ~/.claude/skills/
```

## License

MIT License
