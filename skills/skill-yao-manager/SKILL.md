---
name: skill-yao-manager
description: |
  Skill 工程化管理：创建、验证、检查、lint、打包 skill。当用户需要新建 skill、检查 skill 质量、验证 skill 结构、查看上下文大小、打包 skill 时使用。
  触发词：创建 skill、新建 skill、检查 skill、validate skill、skill lint、skill check、skill 打包、skill package、yao。
---

# Skill 工程化管理

通过 `yao_ops.py` 脚本管理 skill 全生命周期。脚本自包含，无外部 Python 包依赖。

## 配置

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `HARNESS_YAO_META_SKILL_DIR` | `<skill_dir>/third_party/yao-meta-skill` | yao-meta-skill 仓库路径 |
| `HARNESS_SKILLS_DIR` | `<project_root>/skills` | skill 存放根目录 |

项目根目录通过 `git rev-parse --show-toplevel` 动态获取，禁止硬编码。

## 前置条件

`skills/skill-yao-manager/third_party/yao-meta-skill/scripts/` 目录存在。若缺失：

```bash
git clone https://github.com/yaojingang/yao-meta-skill.git skills/skill-yao-manager/third_party/yao-meta-skill
```

## 工作流

### Phase 0: 查看已有 skill

```bash
python skills/skill-yao-manager/scripts/yao_ops.py list
```

### Phase 1: 创建新 skill

```bash
python skills/skill-yao-manager/scripts/yao_ops.py init <name> --desc "描述（含触发词）" [--title "显示标题"]
```

创建后编辑 `skills/<name>/SKILL.md`，填入实际工作流指令。

### Phase 2: 质量检查

逐项检查或一次全检：

```bash
# 结构验证
python skills/skill-yao-manager/scripts/yao_ops.py validate <name>

# lint 规范
python skills/skill-yao-manager/scripts/yao_ops.py lint <name>

# 上下文大小
python skills/skill-yao-manager/scripts/yao_ops.py context-size <name>

# 全面检查（validate + context_size + resource_boundary）
python skills/skill-yao-manager/scripts/yao_ops.py check-all <name>
```

### Phase 3: 打包发布

```bash
python skills/skill-yao-manager/scripts/yao_ops.py package <name> [--platform generic] [--zip]
```

### Phase 4: 批量巡检

对所有已注册 skill 执行质量检查：

```bash
python skills/skill-yao-manager/scripts/yao_ops.py scan
```

## 错误处理

- `FileNotFoundError: scripts 目录不存在` → 执行前置条件中的 git clone
- `validate` 失败 → 检查 SKILL.md frontmatter 是否包含 `name` 和 `description`
- `context_size` 超标 → 拆分 SKILL.md，将详细内容移入 `references/` 目录
- `resource_boundary` 失败 → 检查是否引用了 skill 目录外的文件

## 适用范围

Do not use this skill for:
- 直接执行业务开发任务（应使用对应业务 skill）
- 管理 skill 运行时依赖或第三方包
- 监控 skill 执行效果（使用 health skill）
