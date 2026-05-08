# Domain: Large Codebase Review

通用大代码库质量和安全审计。适用于任何 >100K 行的代码库。

## 前置条件

- 本地有目标代码库 clone
- 通过 `--source-path` 指定根目录

## enumerate

### 方法

从高层结构出发，识别需要审计的区域。

**初始攻击面枚举步骤**：

1. **目录结构扫描**
   ```bash
   find $SRC -type f -name "*.{ts,js,py,go,rs,c,java}" | wc -l
   tree $SRC -L 2 -d
   ```

2. **热点文件识别**（最常修改 = 最可能有问题）
   ```bash
   git log --since="6 months ago" --name-only --pretty=format: | sort | uniq -c | sort -rn | head -20
   ```

3. **复杂度热点**
   ```bash
   # 最大文件
   find $SRC -name "*.ts" -exec wc -l {} + | sort -rn | head -20
   # 深嵌套
   grep -rn "^        " $SRC/src/ | cut -d: -f1 | sort | uniq -c | sort -rn | head -10
   ```

4. **安全敏感区域**
   ```bash
   grep -rn "password\|secret\|token\|api.key\|auth" $SRC/src/ | cut -d: -f1 | sort -u
   grep -rn "eval\|exec\|dangerouslySetInnerHTML\|innerHTML" $SRC/src/
   grep -rn "sql\|query\|SELECT\|INSERT\|DELETE" $SRC/src/
   ```

5. **依赖风险**
   ```bash
   # 过时依赖
   npm outdated 2>/dev/null || pip list --outdated 2>/dev/null
   # 已知漏洞
   npm audit 2>/dev/null || pip-audit 2>/dev/null
   ```

### 候选输出示例

```json
[
  {"name": "auth module complexity", "hypothesis": "认证模块有超大函数和深嵌套，可能含逻辑漏洞", "difficulty": 2, "method": "读取 auth/ 目录所有文件，分析控制流"},
  {"name": "SQL injection surface", "hypothesis": "动态 SQL 拼接可能存在注入", "difficulty": 1, "method": "grep 字符串拼接 + SQL 关键字"},
  {"name": "unused exports", "hypothesis": "导出但未使用的函数增加攻击面", "difficulty": 1, "method": "静态分析 export/import 交叉引用"},
  {"name": "error handling gaps", "hypothesis": "catch 块中静默吞掉错误", "difficulty": 1, "method": "grep empty catch blocks"}
]
```

## probe

### 浅探测步骤

1. **量化** — 该区域有多少文件、多少行代码？
2. **采样** — 读取 2-3 个代表性文件，快速扫描
3. **模式匹配** — 用 grep/ast-grep 搜索已知危险模式
4. **判定** — 该区域是否确实有问题？严重程度如何？

### 判定标准

- **success**: 确认存在可修复的具体问题（有文件路径 + 行号）
- **failed**: 该区域代码质量良好，无明显问题
- **blocked**: 代码过于复杂，需要运行测试或更深理解

### 语言特定 probe 工具

| 语言 | 工具 |
|------|------|
| TypeScript/JS | ast-grep, eslint --format json, tsc --noEmit |
| Python | ast-grep, ruff check, mypy |
| Go | ast-grep, go vet, staticcheck |
| Rust | ast-grep, clippy, cargo audit |
| C/C++ | ast-grep, cppcheck, scan-build |

## drill

### 深入分析

1. **读取完整模块** — 理解上下文和数据流
2. **追踪调用链** — 从入口到危险操作的完整路径
3. **构造 PoC** — 对安全问题：写出触发条件
4. **评估影响** — 这个问题的实际危害是什么？

### 子节点类型

- 具体的 bug/漏洞 → 产出修复建议
- 架构性问题 → 产出重构方案
- 依赖问题 → 产出升级/替换方案

## reflect

### 审计策略调整

| 发现模式 | 调整方向 |
|----------|----------|
| 多处重复同类问题 | 用 ast-grep 全量扫描该模式 |
| 测试覆盖率低的模块 | 优先审计无测试的代码 |
| 近期大量修改的文件 | 升级为高优先级 |
| 安全问题集中在某层 | 深入该层的所有组件 |

### 终止条件

对于质量审计（非安全），当以下条件满足时视为完成：
- 已覆盖 >80% 的高热点文件
- 未发现新的 CRITICAL/HIGH 问题连续 5 轮
- 所有已发现问题已有修复建议
