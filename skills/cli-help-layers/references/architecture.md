# 整体信息架构

## 顶层命令与子命令的组织原则

采用 **名词-动词** 二级结构作为主模型，与 `docker container ls`、`kubectl get pods` 一脉相承：

```plaintext
<tool> <resource> <action> [options] [positional-args]
```

组织规则：

| 规则 | 说明 | 示例 |
| --- | --- | --- |
| R1: 资源优先 | 第一级子命令是资源/领域名词 | `feishu doc`, `feishu task`, `feishu user` |
| R2: 动作次之 | 第二级子命令是动作动词 | `feishu doc create`, `feishu doc search` |
| R3: 高频动作可提升 | 使用频率极高（>60%）的动作可作为顶层别名 | `feishu search` → `feishu doc search` |
| R4: CRUD 动词统一 | 增删改查使用固定动词集 | `create` / `delete` / `update` / `get` / `list` |
| R5: 子命令深度 ≤ 3 | 超过 3 层嵌套应拍平或使用选项替代 | `feishu doc comment list` 可以，但不再往下加层级 |

**何时用子命令 vs 选项/flag：**

| 场景 | 推荐方式 | 原因 |
| --- | --- | --- |
| 操作语义不同（创建 vs 删除） | 子命令 | 动词不同意味着参数集不同 |
| 操作语义相同，输出格式不同 | 选项 `--format` | 核心逻辑一致，仅表现层差异 |
| 布尔化的行为修饰（是否静默） | flag `--quiet` | 不影响核心参数结构 |
| 对同一资源的不同视图（摘要 vs 详情） | 选项 `--detail` 或 flag | 资源相同，粒度不同 |

## 命名规则

### 命令与子命令命名

| 规则 | 正例 | 反例 |
| --- | --- | --- |
| 全小写，用连字符分词 | `doc-comment` | `docComment`, `DocComment` |
| 动词用现在时祈使句 | `create`, `list`, `search` | `creating`, `listed` |
| 避免缩写，除非缩写更知名 | `list`（而非 `ls`） | `rm`（在 AI-First 场景下优先用 `delete`） |
| 单数名词表示资源类型 | `feishu doc` | `feishu docs` |

### 参数命名

```plaintext
长选项：--<noun-phrase>      例如 --output-format, --max-results
短选项：-<single-char>       例如 -o, -n（仅为高频参数设置）
```

| 规则 | 说明 |
| --- | --- |
| 长选项全小写连字符 | `--output-format` 而非 `--outputFormat` |
| 短选项仅分配给使用频率 top-5 的参数 | 减少记忆负担 |
| 布尔 flag 不接受值 | `--verbose` 而非 `--verbose=true` |
| 否定式 flag 使用 `--no-` 前缀 | `--no-cache` |
| 赋值使用空格或 `=` | `--format json` 或 `--format=json` 均合法 |

### 别名规则

```plaintext
# 别名定义格式（在 man 文档中声明）
ALIASES:
  feishu search    → feishu doc search
  feishu cat       → feishu doc get --format=plain
```

规则：

- 每个别名必须在 man 文档中有明确的映射声明
- 别名不引入新参数，仅做子命令 + 默认选项的组合快捷方式
- 在 help 输出中，别名以 `alias:` 标签标注
