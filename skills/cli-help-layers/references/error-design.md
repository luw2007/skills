# 错误与诊断信息设计

## 错误信息的标准格式

每条错误输出严格遵循以下结构：

```plaintext
ERROR [<code>] <name>: <一句话描述>
  Trigger:  <触发条件>
  Fix:      <修复建议>
  Example:  <正确的命令示例>
```

实际输出示例：

```plaintext
ERROR [E1002] CONFLICT_LOCATION: 不能同时指定 --folder 和 --wiki
  Trigger:  feishu doc create "标题" --folder fldrXXX --wiki wikcnYYY
  Fix:      移除 --folder 或 --wiki 中的一个
  Example:  feishu doc create "标题" --wiki wikcnYYY
```

## 错误码编码规则

```plaintext
E<CATEGORY><SEQUENCE>

类别码：
  1xxx  参数与输入错误（客户端可修复）
  2xxx  认证与权限错误
  3xxx  资源状态错误（不存在、已锁定、冲突）
  4xxx  速率与配额限制
  5xxx  服务端内部错误（客户端无法修复）
```

## 在各层文档中嵌入错误信息的策略

| 文档层级 | 展示内容 | 数量 |
| --- | --- | --- |
| usage | 不展示错误 | 0 |
| help | COMMON ERRORS 区块，列出最高频的 3-5 个错误 | 3-5 |
| sub-command help | 该子命令特有的错误，可引用通用错误 | 2-3 |
| man | ERRORS 区块，完整错误码清单 | 全部 |

## 最常见错误的展示格式

在 help 和 sub-command help 中，使用紧凑表格格式：

```plaintext
COMMON ERRORS:
  CODE   NAME              DESCRIPTION                    FIX
  E1001  TITLE_TOO_LONG    标题超过 255 字符               缩短标题
  E1002  CONFLICT_LOCATION --folder 与 --wiki 互斥        只保留一个
  E1003  EMPTY_STDIN       --stdin 但无输入                检查管道数据
```

在 man 中使用完整格式（含 Trigger + Fix + Example）。
