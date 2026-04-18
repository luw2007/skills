# Man 文档规范

Man 文档是命令的完整参考。只有当 agent 遇到 help 无法覆盖的边界场景（罕见参数组合、完整错误码清单、字段级 schema）时才需要查阅。

## 章节结构

```plaintext
@MAN <command-path>

NAME
  <command-path> — <一句话描述>

SYNOPSIS
  <完整语法，含所有参数和子命令分支>

DESCRIPTION
  <完整的功能描述，含：>
  - 核心行为
  - 认证与权限要求
  - 幂等性说明
  - 与其他命令的关系
  - 版本兼容性说明

OPTIONS
  <所有选项的完整列表，每个选项包含：>
  --<name>, -<short>
    Type:       <类型>
    Required:   <yes|no>
    Default:    <默认值>
    Constraint: <取值约束，如范围、正则、互斥关系>
    Since:      <引入版本>
    Desc:       <完整说明>

ARGUMENTS
  <所有位置参数的完整列表，结构同 OPTIONS>

ENUMS
  <所有枚举类型的完整值列表>
  --<option>:
    <value>   <说明>   [since: v1.2]   [deprecated: use <alt>]

SCHEMA
  <结构化输入/输出的 JSON Schema 表示>
  Input:
    {
      "title": {"type": "string", "maxLength": 255, "required": true},
      ...
    }
  Output:
    {
      "doc_id": {"type": "string"},
      ...
    }

EXAMPLES
  <分类示例，按复杂度递增排列>
  ## Basic
  ...
  ## Advanced
  ...
  ## Pipeline
  ...
  ## Error Recovery
  ...

EXIT CODES
  0     成功
  1     通用错误
  2     参数错误（缺失或非法）
  3     认证失败
  4     权限不足
  5     资源未找到
  6     冲突（互斥参数、资源已存在）
  7     速率限制
  8     服务端错误

ERRORS
  <完整错误码清单>
  CODE   NAME                 TRIGGER                           RECOVERY
  ─────────────────────────────────────────────────────────────────────────
  E1001  TITLE_TOO_LONG       title 超过 255 字符                缩短 title
  ...

CAVEATS
  <使用注意事项、已知限制>

COMPATIBILITY
  <版本变更记录中影响行为的 breaking changes>

SEE ALSO
  <相关命令列表>
```

## SCHEMA 区块的写法建议

为便于 LLM 抽取结构化信息，SCHEMA 区块使用 **JSON Schema draft-07** 格式。关键原则：

| 原则 | 说明 |
| --- | --- |
| 显式 required | 在 schema 顶层列出 required 数组，不依赖上下文推断 |
| 显式 type | 每个字段必须标注 type，即使看似自明 |
| enum 内联 | 枚举值直接写入字段定义，不外部引用 |
| description 字段 | 每个字段加 description，≤ 40 字符 |
| 示例值 | 使用 `"example"` 字段给出一个典型值 |

```json
{
  "title": {
    "type": "string",
    "maxLength": 255,
    "required": true,
    "description": "文档标题",
    "example": "周报 2026-W12"
  }
}
```
