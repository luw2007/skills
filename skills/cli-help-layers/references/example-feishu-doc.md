# 完整示例：feishu doc 命令族

以下以 `feishu doc` 为例，展示规范的完整实践。

## feishu doc — Usage（`$ feishu doc`）

```plaintext
@USAGE feishu doc

BRIEF: 飞书云文档的增删改查。

SYNTAX:
  feishu doc <action> [options]

ACTIONS:
  create    创建新文档
  get       获取文档内容
  update    修改文档内容
  delete    删除文档
  search    搜索文档
  list      列出子文档

EXAMPLES:
  # 创建文档
  feishu doc create "周报"

  # 获取文档内容
  feishu doc get wikcnXXXX --format markdown

  # 搜索我创建的文档
  feishu doc search --query "设计方案" --owner me
```

## feishu doc create — Help（`$ feishu doc create --help`）

```plaintext
@HELP feishu doc create

BRIEF: 创建一篇新的飞书云文档。

SYNTAX:
  feishu doc create <title> [--folder <token>] [--wiki <token>] [--format plain|markdown] [--stdin] [--tag <tag>...]

DESCRIPTION:
  在飞书云空间创建一篇新文档。默认创建在个人空间根目录，可通过 --folder 或 --wiki
  指定位置。二者互斥。创建成功后输出文档 ID 和访问 URL。

OPTIONS:
  名称              类型        必填  默认值      说明
  ─────────────────────────────────────────────────────────
  <title>           string      是    -           文档标题（1-255 字符）
  --folder, -f      token       否    ~           父文件夹 token
  --wiki, -w        token       否    -           知识库节点 token（与 --folder 互斥）
  --format          enum        否    markdown    内容格式
  --stdin           flag        否    false       从标准输入读取正文
  --tag             string[]    否    []          标签，可多次指定

ENUMS:
  --format:
    plain       纯文本
    markdown    Markdown + 飞书扩展语法

COMMON EXAMPLES:
  # 最简创建
  feishu doc create "标题"

  # [RECOMMENDED] 在知识库下创建 Markdown 文档
  feishu doc create "API 规范" --wiki wikcnXXXX --format markdown

  # 带标签创建
  feishu doc create "复盘" --tag retro --tag 2026-Q1

  # [PIPELINE] 从文件读取内容
  cat draft.md | feishu doc create "设计文档" --wiki wikcnXXXX --stdin

  # [PIPELINE] 创建后立即追加内容
  ID=$(feishu doc create "空白文档") && feishu doc update $ID --append "## 第一章"

COMMON ERRORS:
  CODE   NAME              DESCRIPTION                    FIX
  E1001  TITLE_TOO_LONG    标题超过 255 字符               缩短标题
  E1002  CONFLICT_LOCATION --folder 与 --wiki 互斥        只保留一个
  E1003  EMPTY_STDIN       --stdin 但无输入                检查管道数据

SEE ALSO:
  feishu doc update    修改文档内容
  feishu doc get       获取文档内容
```

## feishu doc create — Man（`$ feishu doc create --man`）

```plaintext
@MAN feishu doc create

NAME
  feishu doc create — 创建一篇飞书云文档

SYNOPSIS
  feishu doc create <title>
    [--folder|-f <folder-token>]
    [--wiki|-w <wiki-node-token>]
    [--wiki-space <space-id>]
    [--format plain|markdown]
    [--stdin]
    [--tag <tag>]...
    [--quiet|-q]
    [--output json|text]

DESCRIPTION
  在飞书云空间创建一篇新文档并返回文档元信息。

  位置优先级：--wiki > --wiki-space > --folder > 个人空间根目录。
  --wiki 和 --folder 互斥，同时指定会返回 E1002 错误。
  --wiki-space 为知识空间 ID，特殊值 "my_library" 表示个人知识库。

  创建操作是幂等的：相同标题和位置可重复创建，每次生成新文档。
  需要对目标文件夹/知识库有写入权限，否则返回 E2002。

OPTIONS
  <title>
    Type:       string
    Required:   yes
    Constraint: 1-255 字符，不可包含制表符和换行符
    Desc:       文档标题

  --folder, -f
    Type:       string
    Required:   no
    Default:    ~ (个人空间根目录)
    Constraint: 格式 ^fldr[A-Za-z0-9]+$
    Since:      v1.0
    Desc:       目标文件夹 token

  --wiki, -w
    Type:       string
    Required:   no
    Default:    -
    Constraint: 格式 ^wikcn[A-Za-z0-9]+$，与 --folder 互斥
    Since:      v1.0
    Desc:       知识库节点 token

  --wiki-space
    Type:       string
    Required:   no
    Default:    -
    Constraint: 知识空间 ID 或特殊值 "my_library"，与 --wiki 互斥
    Since:      v1.2
    Desc:       知识空间 ID

  --format
    Type:       enum
    Required:   no
    Default:    markdown
    Values:     plain | markdown
    Since:      v1.0
    Desc:       正文内容格式

  --stdin
    Type:       flag
    Required:   no
    Default:    false
    Since:      v1.0
    Desc:       从标准输入读取正文内容

  --tag
    Type:       string[]
    Required:   no
    Default:    []
    Constraint: 每个 tag 1-50 字符，最多 20 个
    Since:      v1.1
    Desc:       文档标签，可多次指定

  --quiet, -q
    Type:       flag
    Required:   no
    Default:    false
    Since:      v1.0
    Desc:       静默模式，仅输出 doc_id

  --output
    Type:       enum
    Required:   no
    Default:    text
    Values:     json | text
    Since:      v1.0
    Desc:       输出格式

SCHEMA
  Input:
    {
      "title":      {"type": "string", "maxLength": 255, "required": true, "description": "文档标题", "example": "周报 2026-W12"},
      "folder":     {"type": "string", "pattern": "^fldr[A-Za-z0-9]+$", "description": "文件夹 token"},
      "wiki":       {"type": "string", "pattern": "^wikcn[A-Za-z0-9]+$", "description": "知识库节点 token"},
      "wiki_space": {"type": "string", "description": "知识空间 ID"},
      "format":     {"type": "string", "enum": ["plain", "markdown"], "default": "markdown"},
      "stdin":      {"type": "boolean", "default": false},
      "tag":        {"type": "array", "items": {"type": "string", "maxLength": 50}, "maxItems": 20},
      "quiet":      {"type": "boolean", "default": false},
      "output":     {"type": "string", "enum": ["json", "text"], "default": "text"}
    }
  Output:
    {
      "doc_id":     {"type": "string", "description": "文档 token", "example": "doxcnABCD1234"},
      "url":        {"type": "string", "format": "uri", "description": "访问链接"},
      "created_at": {"type": "string", "format": "date-time"}
    }

EXAMPLES
  ## Basic
  # 最简创建
  feishu doc create "日报"

  # 指定位置
  feishu doc create "设计文档" --wiki wikcnXXXX

  ## Advanced
  # 创建后获取 JSON 输出
  feishu doc create "API 文档" --wiki wikcnXXXX --output json

  # 多标签
  feishu doc create "复盘" --tag retro --tag backend --tag 2026-Q1

  ## Pipeline
  # [PIPELINE] 从文件创建
  cat README.md | feishu doc create "README 副本" --stdin --format markdown

  # [PIPELINE] 批量创建
  for name in "文档A" "文档B" "文档C"; do feishu doc create "$name" --quiet; done

  ## Error Recovery
  # [ERROR RECOVERY] E1002: 移除冲突参数后重试
  # 错误: feishu doc create "标题" --folder fldrXX --wiki wikcnYY
  # 修复:
  feishu doc create "标题" --wiki wikcnYY

EXIT CODES
  0     创建成功
  2     参数错误（标题缺失、格式非法、参数冲突）
  3     认证失败
  4     权限不足
  5     目标文件夹/知识库不存在
  8     服务端错误

ERRORS
  CODE   NAME              TRIGGER                               RECOVERY
  E1001  TITLE_TOO_LONG    title 超过 255 字符                    缩短 title
  E1002  CONFLICT_LOCATION --folder 和 --wiki 同时指定            移除一个
  E1003  EMPTY_STDIN       --stdin 但管道无数据                   检查上游命令
  E1010  INVALID_TOKEN     folder/wiki token 格式不合法           检查 token 格式
  E2001  AUTH_EXPIRED      认证 token 已过期                      执行 feishu auth login
  E2002  PERM_DENIED       无目标位置写入权限                      联系空间管理员
  E3001  NOT_FOUND         目标 folder/wiki 不存在                确认 token 有效
  E5001  SERVER_ERROR      飞书服务端异常                          稍后重试

CAVEATS
  - 标题相同不会去重，每次创建生成新文档
  - --stdin 读取的内容大小限制为 20MB
  - 创建操作的 QPS 限制为 5 次/秒

SEE ALSO
  feishu doc get       获取文档内容
  feishu doc update    修改文档内容
  feishu doc delete    删除文档
  feishu doc search    搜索文档
  feishu auth login    登录认证
```
