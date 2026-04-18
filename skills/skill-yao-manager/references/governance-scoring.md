# Governance 评分细则

governance_check.py 对每个 skill 计算 0-100 分的治理评分，决定 maturity_tier 是否符合声明。

## 评分维度

| 维度 | 满分 | 关键条件 |
|------|------|----------|
| metadata_integrity | 20 | manifest 合法、name 一致、version/updated_at/status/maturity_tier 均填写 |
| ownership_and_review | 20 | manifest.owner 非空 +10，review_cadence 合法值 +10 |
| boundary_and_eval | 25 | frontmatter description +5，SKILL.md 含 "do not" 声明 +10，evals/ 目录存在 +10 |
| operational_assets | 20 | agents/interface.yaml +5，references/ 有文件 +5，scripts/ 有文件 +5，factory_components 或 target_platforms 填写 +5 |
| maintenance_evidence | 15 | reports/ +5，evals/history/ 或 failures/ +5，outputs/assets/examples/tests/ +5 |

## maturity_tier 最低分要求

| tier | 最低分 |
|------|--------|
| scaffold | 0 |
| production | 80 |
| library | 85 |
| governed | 90 |

## 提升路径

若评分低于声明 tier 的最低分，优先补充：
1. SKILL.md 添加 "Do not use" 明确排除场景 → +10 (boundary_and_eval)
2. 补充 references/ 参考文档 → +5 (operational_assets)
3. 添加 examples/ 或 tests/ 使用示例 → +5 (maintenance_evidence)
