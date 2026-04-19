# 示例：定位应用启动慢的根因

## 目录

- [元信息](#元信息)
- [探索树](#探索树)
  - [第 1 层 — 瓶颈定位](#第-1-层广度枚举--2026-03-15)
  - [反思 R-01](#反思-r-01第-1-层--第-2-层)
  - [第 2 层 — 迁移优化](#第-2-层广度枚举--2026-03-15)
- [状态输出](#状态输出)
  - [文本摘要](#文本摘要从-statejson-渲染)
  - [state.json](#app-startupstatejson机器可读状态)

---

## 元信息

- **目标**: 将桌面应用的冷启动时间从 8 秒降到 2 秒以内
- **约束**: 不能移除核心功能模块、不能降低首屏渲染质量
- **已确认事实**:
  1. 问题在 v2.5 升级后出现（v2.4 正常 ~1.5s）
  2. Release 和 Debug 构建表现一致
  3. 仅 macOS 复现，Windows 正常

---

## 探索树

### 第 1 层（广度枚举 → 2026-03-15）

**当前层问题**: 8 秒启动耗时的主要瓶颈在哪里？
**策略**: 先排除最容易验证的假设（网络/IO/渲染），把模块初始化留到最后深挖

---

#### 1.1 网络请求阻塞主线程 ⭐ ❌ 失败

| 字段 | 内容 |
|------|------|
| 假设 | 启动时的 API 健康检查或配置拉取阻塞了主线程 |
| 方法 | 断开网络后启动（飞行模式） |
| 预期 | 如果是网络问题，离线应显著加速 |
| 实际 | 离线启动仍然 7.8 秒 |
| 结论 | 网络不是瓶颈 |
| 排除 | **原理不通** — 离线同样慢，与网络无关 |

---

#### 1.2 磁盘 IO 瓶颈 ⭐⭐ ❌ 失败

| 字段 | 内容 |
|------|------|
| 假设 | 读取大量配置文件或资源导致 IO 等待 |
| 方法 | `dtrace` 采集启动期间 IO 调用耗时 |
| 预期 | IO 等待占比 > 50% |
| 实际 | 总 IO 耗时仅 200ms（全程 8s 占比 2.5%） |
| 结论 | IO 不是瓶颈 |
| 排除 | **原理不通** — IO 占比极小 |

---

#### 1.3 模块初始化耗时 ⭐⭐ 🔄 深度探索中

| 字段 | 内容 |
|------|------|
| 假设 | 某个模块的初始化过程异常耗时 |
| 方法 | 在各模块 init 前后插入计时日志 |
| 预期 | 找到一个耗时 > 5s 的模块 |
| 实际 | `storage` 模块初始化耗时 6.2 秒 → 深入 |

##### 1.3.1 插件系统加载 ⭐ ❌ 失败

| 字段 | 内容 |
|------|------|
| 假设 | 第三方插件动态加载耗时 |
| 方法 | `--disable-plugins` 参数启动 |
| 实际 | 无插件仍需 7.5 秒 |
| 排除 | **原理不通** — 插件系统不在关键路径 |

##### 1.3.2 数据库 schema 迁移 ⭐⭐ ✅ 成功（根因确认）

| 字段 | 内容 |
|------|------|
| 假设 | v2.5 引入了 schema 变更，首次启动触发同步迁移 |
| 方法 | 检查 `storage` 模块日志中的迁移记录 |
| 实际 | 日志确认 `Running migration v2.5: add columns...` 耗时 5.8 秒 |
| 结论 | **根因确认** — schema 迁移在主线程同步执行，阻塞了 UI 线程 |
| 证据 | 迁移完成后重启仅需 1.3 秒（与 v2.4 持平） |

##### 1.3.3 缓存预热 💡 待浅探

| 字段 | 内容 |
|------|------|
| 假设 | 应用启动时加载全量缓存到内存 |
| 实际 | 未验证（1.3.2 已定位根因，优先级降低） |

---

#### 1.4 渲染阻塞 ⭐ ❌ 失败

| 字段 | 内容 |
|------|------|
| 假设 | 首屏渲染复杂度导致卡顿 |
| 方法 | 无头模式（headless）启动 |
| 实际 | 无头模式同样 7.9 秒 |
| 排除 | **原理不通** — 与渲染无关 |

---

### 反思 R-01（第 1 层 → 第 2 层）

- **本层排除**: 1.1(网络) 1.2(IO) 1.3.1(插件) 1.4(渲染)
- **成功定位**: 1.3.2 schema 迁移是根因
- **共同模式**: 排除的路径都能在 < 10 分钟内快速验证
- **经验**: "先排最便宜的"策略有效 — 4 个⭐路径各花 5 分钟排除，最终在⭐⭐路径上找到答案

---

### 第 2 层（广度枚举 → 2026-03-15）

**当前层问题**: 如何优化 schema 迁移耗时（5.8s → < 500ms）？
**策略**: 从最简单的异步方案开始

---

#### 2.1 迁移移到后台线程 ⭐ 💡 待浅探

| 字段 | 内容 |
|------|------|
| 假设 | 迁移逻辑本身无需阻塞 UI，可以异步执行 |
| 方法 | 将 migration 放入 worker thread，UI 显示 loading 状态 |
| 预期 | 感知启动时间降到 < 2 秒 |
| 难度 | ⭐ — 改动最小，只需包一层 async |

---

#### 2.2 增量迁移 ⭐⭐ 💡 待浅探

| 字段 | 内容 |
|------|------|
| 假设 | 当前迁移是全表扫描，可以改为增量执行 |
| 方法 | 分析迁移 SQL，拆分为可分批执行的小步骤 |
| 预期 | 每步 < 100ms |
| 难度 | ⭐⭐ — 需要理解 schema 变更细节 |

---

#### 2.3 预编译迁移脚本 ⭐⭐ 💡 待浅探

| 字段 | 内容 |
|------|------|
| 假设 | 迁移在运行时解析和编译 SQL，预编译可提速 |
| 方法 | 将迁移 SQL 预编译为 prepared statements |
| 预期 | 减少 SQL 解析开销 |
| 难度 | ⭐⭐ — 需改动 migration 框架 |

---

### 当前优先队列

```
1. 2.1 后台线程迁移 ⭐  ← 改动最小，先试
2. 2.2 增量迁移     ⭐⭐
3. 2.3 预编译       ⭐⭐
```

---

## 状态输出

### 文本摘要（从 state.json 渲染）

```
═══════════════════════════════════════════════════════
📋 探索树 — 应用启动优化
═══════════════════════════════════════════════════════
🎯 目标: 冷启动 8s → 2s
🚫 约束: 不移除功能模块
═══════════════════════════════════════════════════════

🌳 树 (当前: 第2层)
───────────────────────────────────────────────────────
第1层: 8 秒启动瓶颈在哪？
├── ❌ 1.1 网络阻塞 (⭐) — 离线同样慢
├── ❌ 1.2 磁盘IO (⭐⭐) — IO 仅占 2.5%
├── 🔄 1.3 模块初始化 (⭐⭐) → 深入
│   ├── ❌ 1.3.1 插件加载 — 禁用后仍慢
│   ├── ✅ 1.3.2 schema迁移 — 根因确认(5.8s)
│   └── 💡 1.3.3 缓存预热 — 优先级降低
└── ❌ 1.4 渲染阻塞 (⭐) — 无头同样慢

第2层: 优化 schema 迁移耗时
├── 💡 2.1 后台线程 (⭐) ← 优先
├── 💡 2.2 增量迁移 (⭐⭐)
└── 💡 2.3 预编译 (⭐⭐)
───────────────────────────────────────────────────────

📊 统计: ✅1 ❌4 🔄1 💡4
🎯 焦点: 2.1 后台线程 (⭐ 最易)
💭 策略: 改动最小的异步方案先试
═══════════════════════════════════════════════════════
```

### `app-startup.state.json`（机器可读状态）

```json
{
  "task": "应用启动优化",
  "goal": "将桌面应用的冷启动时间从 8 秒降到 2 秒以内",
  "constraints": ["不能移除核心功能模块", "不能降低首屏渲染质量"],
  "confirmed_facts": [
    "问题在 v2.5 升级后出现（v2.4 正常 ~1.5s）",
    "Release 和 Debug 构建表现一致",
    "仅 macOS 复现，Windows 正常"
  ],
  "current_layer": 2,
  "focus": "2.1",
  "strategy": "改动最小的异步方案先试",
  "stats": { "success": 1, "failed": 4, "active": 1, "pending": 4, "blocked": 0, "skipped": 0 },
  "layers": [
    {
      "id": 1,
      "question": "8 秒启动耗时的主要瓶颈在哪里？",
      "strategy": "先排除最容易验证的假设（网络/IO/渲染），把模块初始化留到最后深挖",
      "created_at": "2026-03-15T10:00:00Z",
      "nodes": [
        {
          "id": "1.1",
          "name": "网络请求阻塞主线程",
          "difficulty": 1,
          "status": "failed",
          "hypothesis": "启动时的 API 健康检查或配置拉取阻塞了主线程",
          "method": "断开网络后启动（飞行模式）",
          "expected": "离线应显著加速",
          "actual": "离线启动仍然 7.8 秒",
          "conclusion": "网络不是瓶颈",
          "evidence": null,
          "exclusion": { "type": "principle", "reason": "离线同样慢，与网络无关" },
          "updated_at": "2026-03-15T10:05:00Z",
          "children": []
        },
        {
          "id": "1.2",
          "name": "磁盘 IO 瓶颈",
          "difficulty": 2,
          "status": "failed",
          "hypothesis": "读取大量配置文件或资源导致 IO 等待",
          "method": "dtrace 采集启动期间 IO 调用耗时",
          "expected": "IO 等待占比 > 50%",
          "actual": "总 IO 耗时仅 200ms（全程 8s 占比 2.5%）",
          "conclusion": "IO 不是瓶颈",
          "evidence": null,
          "exclusion": { "type": "principle", "reason": "IO 占比极小" },
          "updated_at": "2026-03-15T10:15:00Z",
          "children": []
        },
        {
          "id": "1.3",
          "name": "模块初始化耗时",
          "difficulty": 2,
          "status": "active",
          "hypothesis": "某个模块的初始化过程异常耗时",
          "method": "在各模块 init 前后插入计时日志",
          "expected": "找到一个耗时 > 5s 的模块",
          "actual": "storage 模块初始化耗时 6.2 秒",
          "conclusion": null,
          "evidence": null,
          "exclusion": null,
          "updated_at": "2026-03-15T10:30:00Z",
          "children": [
            {
              "id": "1.3.1",
              "name": "插件系统加载",
              "difficulty": 1,
              "status": "failed",
              "hypothesis": "第三方插件动态加载耗时",
              "method": "--disable-plugins 参数启动",
              "expected": null,
              "actual": "无插件仍需 7.5 秒",
              "conclusion": null,
              "evidence": null,
              "exclusion": { "type": "principle", "reason": "插件系统不在关键路径" },
              "updated_at": "2026-03-15T10:35:00Z",
              "children": []
            },
            {
              "id": "1.3.2",
              "name": "数据库 schema 迁移",
              "difficulty": 2,
              "status": "success",
              "hypothesis": "v2.5 引入了 schema 变更，首次启动触发同步迁移",
              "method": "检查 storage 模块日志中的迁移记录",
              "expected": null,
              "actual": "日志确认 Running migration v2.5 耗时 5.8 秒",
              "conclusion": "根因确认 — schema 迁移在主线程同步执行，阻塞了 UI 线程",
              "evidence": "迁移完成后重启仅需 1.3 秒（与 v2.4 持平）",
              "exclusion": null,
              "updated_at": "2026-03-15T10:45:00Z",
              "children": []
            },
            {
              "id": "1.3.3",
              "name": "缓存预热",
              "difficulty": 2,
              "status": "pending",
              "hypothesis": "应用启动时加载全量缓存到内存",
              "method": null,
              "expected": null,
              "actual": null,
              "conclusion": null,
              "evidence": null,
              "exclusion": null,
              "updated_at": "2026-03-15T10:45:00Z",
              "children": []
            }
          ]
        },
        {
          "id": "1.4",
          "name": "渲染阻塞",
          "difficulty": 1,
          "status": "failed",
          "hypothesis": "首屏渲染复杂度导致卡顿",
          "method": "无头模式（headless）启动",
          "expected": null,
          "actual": "无头模式同样 7.9 秒",
          "conclusion": null,
          "evidence": null,
          "exclusion": { "type": "principle", "reason": "与渲染无关" },
          "updated_at": "2026-03-15T10:20:00Z",
          "children": []
        }
      ]
    },
    {
      "id": 2,
      "question": "如何优化 schema 迁移耗时（5.8s → < 500ms）？",
      "strategy": "从最简单的异步方案开始",
      "created_at": "2026-03-15T11:00:00Z",
      "nodes": [
        {
          "id": "2.1",
          "name": "迁移移到后台线程",
          "difficulty": 1,
          "status": "pending",
          "hypothesis": "迁移逻辑本身无需阻塞 UI，可以异步执行",
          "method": "将 migration 放入 worker thread，UI 显示 loading 状态",
          "expected": "感知启动时间降到 < 2 秒",
          "actual": null,
          "conclusion": null,
          "evidence": null,
          "exclusion": null,
          "updated_at": "2026-03-15T11:00:00Z",
          "children": []
        },
        {
          "id": "2.2",
          "name": "增量迁移",
          "difficulty": 2,
          "status": "pending",
          "hypothesis": "当前迁移是全表扫描，可以改为增量执行",
          "method": "分析迁移 SQL，拆分为可分批执行的小步骤",
          "expected": "每步 < 100ms",
          "actual": null,
          "conclusion": null,
          "evidence": null,
          "exclusion": null,
          "updated_at": "2026-03-15T11:00:00Z",
          "children": []
        },
        {
          "id": "2.3",
          "name": "预编译迁移脚本",
          "difficulty": 2,
          "status": "pending",
          "hypothesis": "迁移在运行时解析和编译 SQL，预编译可提速",
          "method": "将迁移 SQL 预编译为 prepared statements",
          "expected": "减少 SQL 解析开销",
          "actual": null,
          "conclusion": null,
          "evidence": null,
          "exclusion": null,
          "updated_at": "2026-03-15T11:00:00Z",
          "children": []
        }
      ]
    }
  ],
  "reflections": [
    {
      "id": "R-01",
      "from_layer": 1,
      "to_layer": 2,
      "excluded": ["1.1", "1.2", "1.3.1", "1.4"],
      "common_failure_pattern": "排除的路径都能在 < 10 分钟内快速验证",
      "overlooked_assumptions": [],
      "new_paths": [
        { "name": "后台线程迁移", "hypothesis": "迁移可异步执行", "difficulty": 1 },
        { "name": "增量迁移", "hypothesis": "全表扫描可拆分", "difficulty": 2 },
        { "name": "预编译", "hypothesis": "SQL 解析是瓶颈", "difficulty": 2 }
      ],
      "created_at": "2026-03-15T10:50:00Z"
    }
  ],
  "updated_at": "2026-03-15T11:00:00Z"
}
```
