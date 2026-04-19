# CLI Help Layers

> CLI 帮助信息分层设计指南 — 让 AI Agent 高效解析和调用 CLI 命令

## 这是什么

CLI Help Layers 定义了一套面向 AI-First 时代的命令行帮助文档设计规范。核心洞察：**传统 CLI 的 `--help` 输出对 LLM 来说信息密度不合理** — 要么太少（缺少示例），要么太多（整页 man page）。

本 skill 提出 **Usage → Help → Man 三层渐进式披露架构**，让 AI Agent 用最少的 token 获取最够用的信息。

## 为什么需要它

| 痛点 | CLI Help Layers 的解决方案 |
|------|--------------------------|
| Agent 调用 `--help` 后拿到大量无关选项，浪费 token | 三层架构：80% 场景只需 `@USAGE` 层（BRIEF + SYNTAX + 3-5 EXAMPLES） |
| 不同 CLI 的帮助格式五花八门，LLM 解析不稳定 | 结构化标记 `@USAGE` / `@HELP` / `@MAN` + 固定区块标签，支持零样本正则提取 |
| 示例不够或示例无代表性，Agent 无法类比推理 | 强制要求示例标签 `[RECOMMENDED]` / `[TEMPLATE]` / `[PIPELINE]`，覆盖典型场景 |
| 错误信息不可解析，Agent 无法自动纠错 | 错误码编码规范 + 各层嵌入策略，Agent 可直接匹配错误码定位解法 |

## 三层架构一览

```
命令不带参数  →  @USAGE   80% 覆盖率   BRIEF + SYNTAX + 3-5 EXAMPLES
-h / --help   →  @HELP    95% 覆盖率   OPTIONS 表 + ENUMS + COMMON ERRORS
--man         →  @MAN    100% 覆盖率   SCHEMA + EXIT CODES + ALL ERRORS + CAVEATS
```

Agent 定位正则：`^@(USAGE|HELP|MAN)\s+(.+)$`

## 设计理念

1. **渐进式披露** — 信息密度逐层递增，Agent 多数场景只需前两层
2. **示例即规范** — 借鉴 tldr，每层文档以可执行示例为锚点
3. **结构化优先** — 固定分隔符与格式约定，便于 LLM 零样本抽取

## 参考文档

| 文件 | 内容 |
|------|------|
| `references/architecture.md` | 命名规则、名词-动词组织 |
| `references/usage-spec.md` | Usage 层模板 + 示例挑选原则 |
| `references/help-spec.md` | Help 层 OPTIONS 表 + 枚举 + Sub-command |
| `references/man-spec.md` | Man 层 SCHEMA + EXIT CODES + 完整错误码 |
| `references/error-design.md` | 错误码编码 + 各层嵌入策略 |
| `references/agent-friendly.md` | 文案风格 + 标记系统 + 披露流程 |
| `references/checklist.md` | 五维度 checklist |
| `references/example-feishu-doc.md` | feishu doc 命令族三层完整实践 |

## 安装

```bash
npx skills add luw2007/skills --skill cli-help-layers
```

## License

MIT
