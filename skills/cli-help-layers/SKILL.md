---
name: cli-help-layers
description: |
  CLI Help Layers 帮助信息分层设计指南。在设计或编写 CLI 工具的帮助文档（usage、help、man）时使用。
  适用于需要让 AI Agent 高效解析和调用 CLI 命令的场景：命令结构设计、参数命名、渐进式披露、示例覆盖策略、错误信息设计等。
  触发词：CLI 文档设计、帮助信息设计、CLI help layers、agent 友好 CLI、命令行规范、usage/help/man 设计。
metadata:
  source: https://bytedance.larkoffice.com/wiki/Wu6pwTlLUioB6lk1nWIceykLnef
---

# CLI Help Layers：帮助信息分层设计指南

为 AI-First CLI 的命令行交互与文档体系提供设计指引。核心读者：人类开发者 + LLM/Agent。

## 三条设计理念

1. **渐进式披露**：usage → help → man，信息密度逐层递增，agent 多数场景只需前两层
2. **示例即规范**：借鉴 tldr，每层文档以可执行示例为锚点
3. **结构化优先**：固定分隔符与格式约定，便于 LLM 零样本抽取

## 四层信息架构

| 触发方式 | 层级 | 覆盖率 | 内容 |
|---|---|---|---|
| 命令不带参数 | `@USAGE` | 80% | BRIEF + SYNTAX + 3-5 EXAMPLES |
| `-h` / `--help` | `@HELP` | 95% | OPTIONS 表 + ENUMS + COMMON ERRORS |
| 子命令 `--help` | `@HELP sub` | 98% | 特有选项 + INHERITED OPTIONS + TEMPLATE |
| `--man` | `@MAN` | 100% | SCHEMA + EXIT CODES + ALL ERRORS + CAVEATS |

## 结构化标记

```
@USAGE <path>  / @HELP <path>  / @MAN <path>   → 层级标识
BRIEF: / SYNTAX: / OPTIONS: / ENUMS: / EXAMPLES: / ERRORS:  → 区块标签
# [RECOMMENDED] / [TEMPLATE] / [PIPELINE] / [ADVANCED]      → 示例标签
```

Agent 定位正则：`^@(USAGE|HELP|MAN)\s+(.+)$`，区块：`^([A-Z ]+):$`

## 工作流

设计或审查 CLI 帮助文档时：

1. **确定命令结构** → 参考 `references/architecture.md`（命名规则、名词-动词组织）
2. **编写 Usage** → 参考 `references/usage-spec.md`（模板 + 示例挑选原则）
3. **编写 Help** → 参考 `references/help-spec.md`（OPTIONS 表 + 枚举 + Sub-command Help）
4. **编写 Man** → 参考 `references/man-spec.md`（SCHEMA + EXIT CODES + 完整错误码）
5. **设计错误信息** → 参考 `references/error-design.md`（错误码编码 + 各层嵌入策略）
6. **Agent 友好性优化** → 参考 `references/agent-friendly.md`（文案风格 + 标记系统 + 披露流程）
7. **对照检查** → 参考 `references/checklist.md`（五维度 checklist）
8. **参考完整示例** → 参考 `references/example-feishu-doc.md`（feishu doc 命令族三层完整实践）

## 适用范围

Do not use this skill for:
- CLI 工具的实际代码实现（只管文档设计）
- 非命令行的 API 文档设计
- 已有 CLI 工具的运行与调试
