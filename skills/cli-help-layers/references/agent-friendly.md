# Agent 友好的设计原则 + 渐进式披露流程

## 文案风格

| 原则 | 正例 | 反例 |
| --- | --- | --- |
| 避免歧义代词 | "该选项控制输出格式" | "它控制格式" |
| 显式标注必填/选填 | `Required: yes` | "通常需要提供" |
| 使用确定性动词 | "创建一篇文档" | "可以用来创建文档" |
| 参数名自描述 | `--max-results` | `--n` |
| 类型显式标注 | `Type: string` | 不标注类型 |
| 一个概念一个词 | 全文统一用 "token" | 混用 "token / ID / key" |

## 结构化标记与分隔符

```plaintext
@USAGE <path>    → 标识 usage 区块开始
@HELP <path>     → 标识 help 区块开始
@MAN <path>      → 标识 man 区块开始

区块标签（大写，后跟冒号和换行）：
  BRIEF:
  SYNTAX:
  DESCRIPTION:
  OPTIONS:
  ENUMS:
  EXAMPLES:
  ERRORS:
  COMMON ERRORS:
  SCHEMA:
  EXIT CODES:
  INHERITED OPTIONS:
  SEE ALSO:
  CAVEATS:
  COMPATIBILITY:

示例标签（行内注释）：
  # [RECOMMENDED]   推荐模式
  # [TEMPLATE]      可迁移的调用模板
  # [PIPELINE]      管道组合用法
  # [ADVANCED]      高级用法
```

Agent 可通过正则 `^@(USAGE|HELP|MAN)\s+(.+)$` 定位文档层级，通过 `^([A-Z ]+):$` 定位区块。

## 示例覆盖策略

每条命令的示例集合需覆盖以下六类调用模式（在 usage + help + man 三层中分布）：

| 模式 | 层级 | 标签 | 说明 |
| --- | --- | --- | --- |
| 最小调用 | usage | 无 | 仅必填参数 |
| 单选项调用 | usage | 无 | 加一个高频选项 |
| 组合选项 | help | 无 | 2-3 个选项组合 |
| 管道串联 | help | [PIPELINE] | 与其他命令的 stdin/stdout 组合 |
| 调用模板 | sub-command help | [TEMPLATE] | 用 placeholder 展示通用模式 |
| 错误恢复 | man | [ERROR RECOVERY] | 遇到特定错误后的重试命令 |

## 推荐模式的显式标注

当某个示例代表最佳实践或官方推荐的调用方式时，使用 `[RECOMMENDED]` 标签：

```plaintext
EXAMPLES:
  # 创建文档（最简方式）
  feishu doc create "标题"

  # [RECOMMENDED] 创建文档并归入知识库
  feishu doc create "标题" --wiki wikcnXXXX --format markdown
```

agent 在多个可选方案中应优先选择带 `[RECOMMENDED]` 标签的模式。

## 可机器解析的 schema 提取

CLI 应支持以下命令直接输出结构化 schema：

```bash
# 输出命令的完整 JSON Schema
feishu doc create --schema

# 输出所有子命令列表（JSON 数组）
feishu doc --commands
```

输出格式固定为 JSON：

```json
{
  "command": "feishu doc create",
  "args": [
    {"name": "title", "type": "string", "required": true, "position": 0}
  ],
  "options": [
    {"name": "--folder", "short": "-f", "type": "string", "required": false, "default": "~"},
    {"name": "--wiki", "type": "string", "required": false, "conflicts_with": ["--folder"]},
    {"name": "--format", "type": "enum", "values": ["plain", "markdown"], "default": "markdown"}
  ]
}
```

---

## 渐进式披露的完整流程

Agent 调用一条命令的完整信息获取路径：

```plaintext
┌─────────────────────────────────────────────────────────┐
│  Agent 收到任务："创建一篇飞书文档"                        │
│                                                         │
│  Step 1: 读取 usage（$ feishu doc create）               │
│  ┌───────────────────────────────────────┐              │
│  │  BRIEF + SYNTAX + 3-5 EXAMPLES       │  ← 80% 场景  │
│  └───────────────────────────────────────┘              │
│           │                                             │
│           ▼ 参数不确定？                                  │
│  Step 2: 读取 help（--help）                             │
│  ┌───────────────────────────────────────┐              │
│  │  OPTIONS 表 + ENUMS + COMMON ERRORS  │  ← 95% 场景  │
│  └───────────────────────────────────────┘              │
│           │                                             │
│           ▼ 遇到罕见错误或边界参数？                       │
│  Step 3: 读取 man（--man）                               │
│  ┌───────────────────────────────────────┐              │
│  │  SCHEMA + EXIT CODES + ALL ERRORS    │  ← 100% 覆盖 │
│  └───────────────────────────────────────┘              │
└─────────────────────────────────────────────────────────┘
```

### 缓存与预加载建议

| 策略 | 说明 |
| --- | --- |
| 会话初始化时加载 usage | agent 启动时预加载所有命令的 usage（体积小，信息密度高） |
| 按需加载 help | 仅在 usage 不足时请求 help |
| 极少加载 man | 仅在错误恢复或 schema 提取时请求 man |
| schema 缓存 | `--schema` 输出可长期缓存，随版本号更新 |
