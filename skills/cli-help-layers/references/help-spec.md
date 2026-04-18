# Help 规范 + Sub-command Help 规范

## Help 规范

> 命令级：面向常见 use case

Help 是 agent 在 usage 信息不足时的**第二层参考**。它覆盖一条命令的所有参数，并提供更多示例和错误提示。

### 推荐输出结构

```plaintext
@HELP <command-path>

BRIEF: <同 usage>

SYNTAX:
  <command-path> <args> [options]

DESCRIPTION:
  <2-4 句补充说明，涵盖命令的核心行为、前置条件、副作用>

OPTIONS:
  名称              类型        必填  默认值    说明
  ─────────────────────────────────────────────────────────
  <title>           string      是    -         文档标题（1-255 字符）
  --folder, -f      token       否    ~         父文件夹 token，~ 表示个人根目录
  --wiki            token       否    -         知识库节点 token，与 --folder 互斥
  --format          enum        否    markdown  输出格式：plain | markdown
  --stdin           flag        否    false     从标准输入读取正文内容
  --tag             string[]    否    []        标签列表，可多次指定

ENUMS:
  --format:
    plain       纯文本，不含任何标记
    markdown    标准 Markdown + 飞书扩展语法

COMMON EXAMPLES:
  # 创建带标签的文档
  feishu doc create "技术方案" --tag backend --tag infra

  # 在知识库下创建并从文件读取内容
  cat design.md | feishu doc create "设计文档" --wiki wikcnXXXX --stdin

  # 与 feishu doc update 配合使用：先建后写
  DOC_ID=$(feishu doc create "空文档" --format plain) && feishu doc update $DOC_ID --append "补充内容"

COMMON ERRORS:
  E1001  TITLE_TOO_LONG      标题超过 255 字符
         → 缩短标题或将副标题移入正文
  E1002  CONFLICT_LOCATION    同时指定了 --folder 和 --wiki
         → 二者互斥，只保留一个
  E1003  EMPTY_STDIN          使用 --stdin 但未提供输入
         → 确保管道有数据，或移除 --stdin flag

SEE ALSO:
  feishu doc update    修改已有文档内容
  feishu doc get       获取文档内容
  feishu doc search    搜索文档
```

### 「常见 use case」与「高频 use case」的区分

| 维度 | 高频 use case（usage） | 常见 use case（help） |
| --- | --- | --- |
| 数量 | 3-5 个 | 5-10 个 |
| 复杂度 | 简单，1-2 个参数 | 中等，含组合参数或管道 |
| 目标 | 让 agent 快速上手 | 覆盖 95% 的实际调用场景 |
| 选取标准 | 调用频率 top-5 | 频率 top-5 + 易出错场景 + 组合模式 |

### OPTIONS 表的书写要求

每个选项条目必须包含以下信息：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| 名称（长+短） | 是 | 短选项可空 |
| 类型 | 是 | string / int / float / bool / enum / token / string[] / JSON |
| 必填 | 是 | 是 / 否 |
| 默认值 | 是 | 无默认则用 `-` |
| 说明 | 是 | ≤ 60 字符，含取值范围或约束 |

对于**推荐值**（非默认值但在实践中最优的选择），在说明中用 `[推荐]` 标签标注：

```plaintext
  --concurrency     int       否    4         并发数（1-32）[推荐: 8]
```

### 枚举值的完整说明

在 help 的 `ENUMS` 区块中，列出每个枚举选项的所有合法值及其一句话说明：

```plaintext
ENUMS:
  --status:
    open       未处理
    closed     已关闭
    merged     已合并
    draft      草稿（仅创建者可见）
    archived   已归档（只读）
```

---

## Sub-command Help 规范

当一个子命令的参数集与兄弟子命令差异较大，或拥有独立的工作流逻辑时，需要独立的 sub-command help。

### 结构要求

```plaintext
@HELP <command> <sub-command> <action>

BRIEF: <一句话>

PARENT: <command> <sub-command>

SYNTAX:
  <full-command-path> <args> [options]

DESCRIPTION:
  <该子命令特有的行为说明，含前置条件和副作用>

OPTIONS:
  <仅列出该子命令特有的选项，继承自父命令的选项不重复列出>

INHERITED OPTIONS:
  <从父命令继承的选项，仅列出名称，加 "see: <parent> help" 引用>

EXAMPLES:
  # <专用示例 1>
  <command>

  # <专用示例 2: 推荐模式>   ← [RECOMMENDED]
  <command>

  # <调用模板>               ← [TEMPLATE]
  <command-with-placeholders>

ERRORS:
  <该子命令特有的错误码>

SEE ALSO:
  <相关子命令>
```

### 信息分层原则

| 信息类别 | 出现位置 | 说明 |
| --- | --- | --- |
| 继承选项（如 --format, --verbose） | 仅在顶层 help | 子命令中以 INHERITED OPTIONS 引用 |
| 子命令特有选项 | 仅在子命令 help | 不在顶层 help 中出现 |
| 资源级描述（如 "什么是 doc"） | 顶层 help 的 DESCRIPTION | 子命令不重复 |
| 动作级前置条件（如 "需要先创建"） | 子命令 help 的 DESCRIPTION | 明确写出 |
| 错误码 | 通用错误在顶层，专用错误在子命令 | 子命令可引用通用错误 |

### 调用模板设计

为便于 agent 迁移到相似子命令，使用 `[TEMPLATE]` 标签标注模板示例：

```plaintext
EXAMPLES:
  # [TEMPLATE] 对任意资源执行 CRUD 操作的通用模式
  feishu <resource> create <title> [--folder <folder-token>]
  feishu <resource> get <id> [--format json|plain]
  feishu <resource> update <id> --<field> <value>
  feishu <resource> delete <id> [--force]
```
