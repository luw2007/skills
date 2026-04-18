# skill-evolve 演化引擎设计 Spec

> 日期：2026-04-16  
> 状态：Reviewed (v2)  
> 作者：luw2007  

## 1. 定位

**单机本地优先的 Skill 演化引擎**——从 Agent 会话轨迹中自动提取经验、生成 SKILL.md 改进补丁，经 D1-D7 质量门禁验证后暂存待人工确认。

与竞品的差异化：

| 维度 | SkillClaw | Memento-Skills | skill-evolve (本项目) |
|------|-----------|----------------|----------------------|
| 部署模型 | Client-Server + OSS/S3 | 单机闭环 | **单机本地优先** |
| 外部依赖 | OSS/S3 必需 | 无 | **零依赖（纯本地文件系统）** |
| 质量门禁 | A/B 实证验证（夜间真实任务 PK，单调性部署） | 单元测试门控 | **D1-D7 规则审计 + threat_scan + 非降级检查** |
| 安全扫描 | 无专门扫描 | 无 | **threat_scan 集成（20 pattern）** |
| 进化信号 | 多轨迹联合分析（成功+失败保留不变量） | 单轨迹 | **单轨迹（SignalExtractor → PatchGenerator）** |
| Skill 格式 | SKILL.md | 技能文件夹 | **SKILL.md（OpenClaw 兼容）** |
| 可扩展性 | 9+ Agent 原生集成 | 固定架构 | **adapter 接口，内部可接 Bitable/TCC** |

## 2. 用户与场景

### 2.1 目标用户

- **开源用户**：使用 Claude Code / OpenClaw / Trae 编写 Skill 的开发者
- **字节内部用户**：使用 harness 脚手架的团队（通过 adapter 接入 Bitable/TCC）

### 2.2 核心场景

1. **审计场景**：`skill-evolve audit <skill_dir>` → 输出 D1-D7 评分报告
2. **演化场景**：`skill-evolve evolve <skill_dir> --trajectory <session_file>` → 从轨迹生成改进补丁
3. **守护场景**：`skill-evolve watch <skill_dir>` → 监听新轨迹文件自动触发演化
4. **CI 场景**：`skill-evolve audit <skill_dir> --ci` → exit code 门禁

## 3. 架构

```
┌─────────────────────────────────────────────────┐
│                   CLI (click/typer)              │
│  audit │ evolve │ watch │ commit               │
└────────┬────────┬───────┬──────────┬─────────────┘
         │        │       │          │
    ┌────▼────┐   │  ┌────▼────┐    │
    │ Auditor │   │  │ Watcher │    │
    │ (D1-D7) │   │  │ (inotify│    │
    └────┬────┘   │  │ /polling│    │
         │        │  └────┬────┘    │
         │   ┌────▼───────▼───┐    │
         │   │  Evolve Engine  │    │
         │   │  ┌────────────┐ │    │
         │   │  │ Trajectory  │ │    │
         │   │  │ Collector   │ │    │
         │   │  └──────┬─────┘ │    │
         │   │  ┌──────▼─────┐ │    │
         │   │  │ Signal     │ │    │
         │   │  │ Extractor  │ │    │
         │   │  │ (LLM)      │ │    │
         │   │  └──────┬─────┘ │    │
         │   │  ┌──────▼─────┐ │    │
         │   │  │ Patch      │ │    │
         │   │  │ Generator  │ │    │
         │   │  │ (LLM)      │ │    │
         │   │  └──────┬─────┘ │    │
         │   └─────────┼──────┘    │
         │        ┌────▼────┐      │
         └───────►│ Gateway │◄─────┘
                  │ (门禁)   │
                  │ D1-D7   │
                  │ threat  │
                  └────┬────┘
                  ┌────▼────┐
                  │.pending │
                  │evolution│
                  └────┬────┘
                  ┌────▼────┐
                  │ commit  │
                  │ → SKILL │
                  │   .md   │
                  └─────────┘

  ┌─────────────────────────┐
  │   Adapter Interface     │
  │  (可选，不随核心发布)     │
  │  ├─ BitableAdapter      │
  │  ├─ TCCAdapter          │
  │  └─ S3Adapter           │
  └─────────────────────────┘
```

### 3.1 核心模块

| 模块 | 职责 | 输入 | 输出 |
|------|------|------|------|
| **CLI** | 入口分发 | 用户命令 | 子命令路由 |
| **Auditor** | D1-D7 维度评审 | SKILL.md 路径 | 评分报告 JSON |
| **TrajectoryCollector** | 解析 Agent 会话轨迹 | session Markdown/JSON/JSONL | 结构化轨迹对象 |
| **TriggerJudge** | 判定是否值得分析（吸收 should_improve 逻辑） | 轨迹 + feedback 历史 | should_evolve: bool + reason |
| **SignalExtractor** | LLM 分析轨迹，提取信号 | 轨迹 + 当前 SKILL.md | `{invariants: [], fixes: [], new_phases: []}` |
| **PatchGenerator** | LLM 生成 SKILL.md 补丁 | 信号 + 当前 SKILL.md | unified diff patch |
| **Gateway** | 质量门禁 | patch + SKILL.md + Auditor(实例) | pass/fail + 原因 |
| **PendingStore** | 暂存候选补丁 | patch + 元数据 | `.pending_evolution/` 目录 |
| **Watcher** | 文件监听守护进程 | 轨迹目录 | 触发 evolve 管线 |
| **AdapterInterface** | 可扩展接口 | 事件 hook | 外部系统回调 |

### 3.2 LLM 调用设计

通过 `litellm` 统一调用，支持 OpenAI/Anthropic/Bedrock/本地模型。

**调用点 1：SignalExtractor**

```
输入：
- 当前 SKILL.md 全文
- 会话轨迹（截断至 max_tokens）
- 执行结果（成功/失败 + 评分）

输出（结构化 JSON）：
{
  "invariants": ["步骤 X 在所有成功 case 中都被执行，不可删除"],
  "fixes": [{"target": "Phase 2 Step 3", "issue": "缺少错误处理", "suggestion": "添加 fallback"}],
  "new_phases": [{"name": "参数校验", "rationale": "3 次失败均因输入格式错误"}]
}
```

**调用点 2：PatchGenerator**

```
输入：
- 当前 SKILL.md 全文
- SignalExtractor 输出
- 约束：仅修改必要部分，保持格式一致

输出：
- unified diff 格式的 patch
- 变更说明（1-2 句）
```

### 3.2.1 LLM 错误处理

| 错误类型 | 处理策略 |
|----------|----------|
| JSON parse 失败 | 重试 2 次（含格式提示强化），仍失败则跳过本轨迹，记录到 `reports/evolve-errors.json` |
| API 超时/rate limit | 指数退避重试（litellm `num_retries=3`） |
| API key 过期 | 立即报错退出，提示用户检查配置 |
| Patch apply 失败 | 降级为"全文替换模式"（LLM 输出完整 SKILL.md，再 diff），仍失败则标记为需人工处理 |
| 模型名称路由 | litellm 需要前缀（如 `anthropic/claude-sonnet-4-20250514`），config 中自动补全或在文档中说明 |

### 3.3 门禁规则

候选 patch 必须通过以下检查才能进入 `.pending_evolution/`：

1. **D6 threat_scan**：patch 内容 + SignalExtractor 中间产物均不含 prompt 注入模式
2. **格式校验**：patch 应用后的 SKILL.md 仍然是合法 Markdown
3. **D1-D7 非降级**：应用 patch 后各维度评分不低于应用前（Gateway 内部调用 Auditor：`audit_before → apply_patch(tempfile) → audit_after → compare_scores`）
4. **diff 大小限制**：单次 patch 变更行数 ≤ 50（防止 LLM 幻觉产生大面积重写）

> 注：Auditor 为纯规则引擎（不使用 LLM），每次 evolve 含 2 次 audit 调用，耗时 <100ms。支持审计结果缓存（同一 SKILL.md hash 复用）。

## 4. 数据流

### 4.1 演化管线（evolve 命令）

```
session_trajectory.md
        │
        ▼
TrajectoryCollector.parse()
        │ → StructuredTrajectory
        ▼
TriggerJudge.should_evolve(trajectory, feedback_history)
        │ → {should: bool, reason: str}
        │   (skip 则记录原因并退出)
        ▼ (should=true)
SignalExtractor.extract(trajectory, skill_md)
        │ → Signals{invariants, fixes, new_phases}
        ▼
Gateway.scan_signals(signals)
        │ → threat_scan 中间产物检查
        ▼ (pass)
PatchGenerator.generate(signals, skill_md)
        │ → Patch(diff, description)
        ▼
Gateway.validate(patch, skill_md)
        │ → pass / fail(reasons)
        ▼ (pass)
PendingStore.save(patch, metadata)
        │ → .pending_evolution/{timestamp}-{hash}.json
        ▼
[用户] skill-evolve pending commit → 应用 patch 到 SKILL.md
```

### 4.2 审计管线（audit 命令）

```
SKILL.md
   │
   ▼
Auditor.scan_structure()     → D1-D7 各维度检测
   │
   ▼
Auditor.score()              → 各维度等级 + 总分
   │
   ▼
Auditor.suggest()            → 可操作改进建议列表
   │
   ▼
输出 JSON / 终端表格 / CI exit code
```

### 4.3 轨迹格式

支持三种输入格式，TrajectoryCollector 通过以下优先级自动检测：
1. 扩展名 `.jsonl` → 格式 C
2. 扩展名 `.json` + 顶层有 `session_id` → 格式 B
3. 扩展名 `.md` 且含 `## User` / `## Assistant` → 格式 A
4. 用户可通过 `--format` 显式指定

**格式 A：Markdown 会话记录**（自定义格式，需手动标注 result）
```markdown
## User
请帮我分析这个 API 的性能问题

## Assistant
我来分析一下...
[tool_call: Read("src/api.py")]
...

## Execution Result
rating: 3
category: general
turns: 8
```

**格式 B：JSON 结构化轨迹**（skill-evolve 原生格式）
```json
{
  "session_id": "abc123",
  "skill_name": "sre-quality",
  "messages": [...],
  "result": {"rating": 3, "category": "general", "turns": 8}
}
```

**格式 C：Claude Code JSONL**（`~/.claude/projects/` 下的原生导出）
```jsonl
{"type":"human","message":{"role":"user","content":"..."}}
{"type":"assistant","message":{"role":"assistant","content":"...","tool_calls":[...]}}
```

> 注：格式 C 中不包含 `result` 字段。`rating` 需用户通过 `--rating` CLI 参数提供，或由 TriggerJudge 基于轨迹内容自动推断（启发式规则：含 error/exception 关键词 → category=error，对话轮数作为 turns）。

## 5. 目录结构（重构后）

```
skill-evolve/                          # 改名：skill-improver → skill-evolve
├── SKILL.md                           # 保留：自身的 Skill 定义
├── manifest.json                      # 更新：版本 2.0.0
├── pyproject.toml                     # 新增：包管理 + CLI 入口
├── agents/
│   └── interface.yaml                 # 更新：新增 evolve 触发词
├── evals/
│   └── trigger_cases.json             # 更新：新增 evolve 相关用例
├── src/
│   └── skill_evolve/
│       ├── __init__.py
│       ├── cli.py                     # CLI 入口（audit/evolve/watch/pending）
│       ├── auditor.py                 # D1-D7 审计引擎（纯规则，从 scripts/ 重构）
│       ├── trajectory.py              # 轨迹解析器（格式 A/B/C 自动检测）
│       ├── trigger_judge.py           # 触发判定（吸收 should_improve 逻辑）
│       ├── signal_extractor.py        # LLM 信号提取
│       ├── patch_generator.py         # LLM 补丁生成
│       ├── gateway.py                 # 质量门禁
│       ├── pending_store.py           # .pending 管理
│       ├── watcher.py                 # 文件监听守护
│       ├── threat_scan.py             # 安全扫描（从 scripts/ 迁移）
│       ├── llm.py                     # LLM 调用封装（litellm）
│       ├── config.py                  # 配置管理
│       └── adapters/
│           ├── __init__.py
│           └── base.py                # AdapterInterface 抽象基类
├── tests/
│   ├── test_auditor.py
│   ├── test_trajectory.py
│   ├── test_signal_extractor.py
│   ├── test_gateway.py
│   └── fixtures/                      # 测试用轨迹文件
├── scripts/                           # 保留旧脚本作为兼容层（deprecated）
│   └── ...
└── docs/
    └── 2026-04-16-skill-evolve-engine-design.md  # 本文件
```

## 6. 配置

```toml
# pyproject.toml 中的默认配置
[project]
requires-python = ">=3.10"

[tool.skill-evolve]
llm_model = "anthropic/claude-sonnet-4-20250514"   # litellm 格式，含 provider 前缀
llm_base_url = ""                      # 留空则用 litellm 默认
max_trajectory_tokens = 16000          # 轨迹截断（头尾保留、中间截断）
max_patch_lines = 50                   # 单次 patch 上限
pending_dir = ".pending_evolution"     # 暂存目录
watch_patterns = ["*.md", "*.json", "*.jsonl"]  # 监听文件模式
adapter = "none"                       # none / bitable / tcc / s3
```

用户可通过以下方式覆盖：
1. `pyproject.toml` 中的 `[tool.skill-evolve]`
2. 环境变量 `SKILL_EVOLVE_*`
3. CLI 参数 `--model`, `--max-patch-lines` 等

## 7. CLI 接口

```bash
# 审计
skill-evolve audit <skill_dir>                    # 终端表格输出
skill-evolve audit <skill_dir> --json             # JSON 输出
skill-evolve audit <skill_dir> --ci               # CI 模式（exit code: 0=达标, 1=不达标）

# 演化
skill-evolve evolve <skill_dir> -t <trajectory>   # 单轨迹演化
skill-evolve evolve <skill_dir> -t <dir>          # 批量轨迹演化
skill-evolve evolve <skill_dir> -t <file> --format jsonl  # 显式指定格式
skill-evolve evolve <skill_dir> -t <file> --rating 2      # 手动提供评分

# 候选管理
skill-evolve pending list <skill_dir>             # 查看候选补丁
skill-evolve pending show <patch_id>              # 查看补丁详情（含 diff 预览）
skill-evolve pending commit <patch_id>            # 应用补丁（检查 base hash 一致性）
skill-evolve pending discard <patch_id>           # 丢弃补丁

# 守护进程
skill-evolve watch <skill_dir> --trajectory-dir <dir>
```

## 8. Adapter 接口

```python
class AdapterInterface(ABC):
    """可扩展接口，内部 adapter 实现不随核心发布。"""

    def on_init(self, config: dict) -> None:
        """初始化回调。内部可初始化 Bitable token 等。"""

    def on_shutdown(self) -> None:
        """关闭回调。清理资源。"""

    def on_error(self, stage: str, error: Exception) -> None:
        """错误回调。stage 为 audit/evolve/commit 之一。"""

    @abstractmethod
    def on_audit_complete(self, skill_dir: Path, report: dict) -> bool:
        """审计完成回调。返回是否成功。内部可回写 Bitable。"""

    @abstractmethod
    def on_evolution_proposed(self, skill_dir: Path, patch: dict) -> bool:
        """候选演化生成回调。返回是否成功。内部可发飞书通知。"""

    @abstractmethod
    def on_evolution_committed(self, skill_dir: Path, patch: dict) -> bool:
        """演化合入回调。返回是否成功。内部可更新 TCC 配置。"""

    @abstractmethod
    def load_trajectories(self, skill_name: str) -> list[Path]:
        """加载轨迹。内部可从 S3/Bitable 拉取。"""
```

## 9. 迁移计划

### 9.1 旧脚本 → 新模块映射

| 旧脚本 | 新模块 | 迁移策略 |
|--------|--------|----------|
| `collect_feedback.py` | `trajectory.py` + CLI `--rating` | 旧脚本的手动参数模式保留为 `evolve --rating` 参数 |
| `should_improve.py` | `trigger_judge.py` | 4 条规则全部迁移，新增基于轨迹内容的启发式推断 |
| `analyze_trajectory.py` | `signal_extractor.py` | 旧的规则三分法作为 LLM 不可用时的 fallback |
| `merge_lessons.py` | `pending_store.py` | 数据格式从 `.pending_lessons.json` 迁移到 `.pending_evolution/` 目录 |
| `threat_scan.py` | `threat_scan.py` | 直接迁移，扩展威胁模式库 |
| `run_retrospective.py` | `cli.py evolve` | 管线编排逻辑吸收到 CLI evolve 命令 |

### 9.2 旧数据迁移

- `reports/feedback-log.json` → 保留只读，新数据写入 `reports/evolve-log.json`
- `.pending_lessons.json` → 运行 `skill-evolve migrate` 一次性转换为 `.pending_evolution/` 格式
- `reports/improvement-log.json` → 合并到 `reports/evolve-log.json`

### 9.3 废弃时间线

- P0 发布：旧脚本加入 `DeprecationWarning`，指引用户迁移到新 CLI
- P2 发布：旧脚本移入 `scripts/_deprecated/`，不再维护
- P4 发布：删除旧脚本

## 10. Watch 模式设计

- **执行模型**：串行队列（FIFO），避免并发 patch 冲突
- **状态持久化**：`.watch_state.json` 记录已处理轨迹的 path + mtime，重启后跳过已处理文件
- **跨平台**：使用 `watchdog` 库（支持 macOS FSEvents + Linux inotify + Windows ReadDirectoryChangesW）
- **冲突检测**：`pending commit` 时检查 patch 的 base SKILL.md SHA256 是否与当前一致，不一致则提示重新生成

## 11. 渐进式发布计划

| 阶段 | 内容 | 交付物 |
|------|------|--------|
| **P0：审计 CLI** | Auditor 重构 + CLI 入口 + CI 模式 | `skill-evolve audit` 可用 |
| **P1：演化核心** | TrajectoryCollector + TriggerJudge + SignalExtractor + PatchGenerator + Gateway | `skill-evolve evolve` 可用 |
| **P2：候选管理** | PendingStore + commit/discard | `skill-evolve pending` 可用 |
| **P3：守护进程** | Watcher + 自动触发 | `skill-evolve watch` 可用 |
| **P4：Adapter** | AdapterInterface + 内部实现 | 字节内部接入 |

## 12. 非目标（明确不做）

- 多用户共享演化（SkillClaw 的地盘）
- 运行时 Agent 拦截（不做 proxy）
- 可视化 Dashboard
- 模型微调 / 蒸馏
