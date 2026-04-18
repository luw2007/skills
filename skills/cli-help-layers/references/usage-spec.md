# Usage 规范

> 入口级：面向高频 use case

## 定位

Usage 是 agent 接触一条命令的**第一份文档**，等价于 tldr 页面。设计目标：agent 读完 usage 后能覆盖 **80% 的日常调用场景**。

| 触发方式 | 展示内容 | 对应层级 |
| --- | --- | --- |
| 输入命令但**不带任何参数**，且命令无法执行 | 最精简的语法摘要和 3-5 个示例 | `@USAGE` |
| 输入命令或子命令并附加 `-h` 或 `--help` | 完整参数表、枚举说明、常见错误 | `@HELP` |
| 输入 `man <command>`，或使用 `-m` / `--man` | JSON Schema、全部错误码、Caveats 等完整参考 | `@MAN` |

简言之：**无参数时给你看够用的，-h 时给你看全的，--man 时给你看所有的。**

## 固定结构

```plaintext
@USAGE <command-path>

BRIEF: <一句话说明，< 1024 字符>

SYNTAX:
  <command-path> <required-arg> [optional-arg] [options]

EXAMPLES:
  # <用例描述，一句话>
  <完整可执行命令>

  # <用例描述>
  <完整可执行命令>

  # <用例描述>
  <完整可执行命令>

ENUMS:
  --<option-name>: <value1> | <value2> | <value3>   # 仅列出高频枚举
```

## Usage 示例

```plaintext
@USAGE feishu doc create

BRIEF: 创建一篇新的飞书云文档。

SYNTAX:
  feishu doc create <title> [--folder <folder-token>] [--wiki <wiki-node>] [--format plain|markdown]

EXAMPLES:
  # 在个人空间创建文档
  feishu doc create "周报 2026-W12"

  # 在指定知识库节点下创建
  feishu doc create "API 设计规范" --wiki wikcnXXXXYYYY

  # 在指定文件夹下创建并指定内容格式
  feishu doc create "会议纪要" --folder fldrTokenABC --format markdown

  # 从标准输入读取 Markdown 内容
  echo "## 标题\n正文" | feishu doc create "草稿" --stdin

ENUMS:
  --format: plain | markdown
```

## 高频 use case 的挑选原则

| 优先级 | 判断标准 | 说明 |
| --- | --- | --- |
| P0 | 最简调用（happy path） | 仅填必填参数的最小用例 |
| P1 | 带一个常用选项的调用 | 覆盖最常被使用的 1 个可选参数 |
| P2 | 组合调用 / 管道用法 | 体现与其他命令的串联模式 |
| P3 | 边界 / 特殊模式 | 如从 stdin 读取、批量操作 |

数量限制：**3-5 个**，不超过 5 个。

## 枚举信息的暴露策略

在 usage 的 `ENUMS` 区块中，仅列出满足以下条件的枚举：

1. 枚举值总数 ≤ 7
2. 该选项在高频用例中出现
3. 枚举值的语义不能从名称自明推断

超过 7 个值的枚举在 usage 中只列出最常用的 3 个并加省略标记：

```plaintext
ENUMS:
  --status: open | closed | merged | ...   # 完整列表见 help
```

## Agent 加载时获取命令描述信息

Agent 启动加载上下文时，调用 command 获取 usage 头部 `BRIEF` 信息，不加载其他信息。BRIEF 基本不变，建议 agent 增加缓存设置版本，定期更新。

```plaintext
@USAGE feishu [options] [command]

BRIEF: Feishu collaboration commands for docs, wiki, calendars, tasks, chat, and data tools
```
