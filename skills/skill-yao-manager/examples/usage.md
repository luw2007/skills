# skill-yao-manager 使用示例

## 示例 1：检查新建 skill 质量

```bash
# 1. 创建新 skill
python skills/skill-yao-manager/scripts/yao_ops.py init my-feature --desc "我的功能 skill，触发词：my-feature"

# 2. 全面检查
python skills/skill-yao-manager/scripts/yao_ops.py check-all my-feature

# 期望输出：✅ validate ✅ context_size ✅ resource_boundary
```

## 示例 2：修复 governance 评分不足

场景：skill 声明 maturity_tier=production，但 governance score 低于 80

```bash
# 诊断
python skills/skill-yao-manager/scripts/yao_ops.py validate my-skill
# 查看 warnings 中的 governance score 和 score_breakdown

# 修复步骤（参考 references/governance-scoring.md）
# 1. 在 SKILL.md 末尾加 "Do not use" 声明 → +10
# 2. 在 references/ 新增文档 → +5
# 3. 在 examples/ 新增示例文件 → +5

# 验证修复
python skills/skill-yao-manager/scripts/yao_ops.py validate my-skill
```

## 示例 3：批量扫描并定位问题

```bash
python skills/skill-yao-manager/scripts/yao_ops.py scan 2>&1 | python3 -c "
import json, sys
data = json.load(sys.stdin)
for s in data:
    if not s['ok']:
        print(f\"{s['skill']}: {s['fails']}\")
"
```

## 示例 4：打包发布到 generic 平台

```bash
python skills/skill-yao-manager/scripts/yao_ops.py package my-skill --platform generic --zip
# 输出到 dist/ 目录
```

## 示例 5：自定义路径

```bash
# 指定自定义 yao-meta-skill 仓库和 skills 目录
HARNESS_YAO_META_SKILL_DIR=/path/to/yao-meta-skill \
HARNESS_SKILLS_DIR=/path/to/skills \
python skills/skill-yao-manager/scripts/yao_ops.py list
```
