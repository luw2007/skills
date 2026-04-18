# 规范检查清单

新增或修改命令时，使用以下 checklist 验证文档完整性。

## Usage 检查

- [ ] 有且仅有一行 BRIEF（≤ 1024 字符）
- [ ] SYNTAX 含完整命令路径和所有必填参数
- [ ] EXAMPLES 数量 3-5 个
- [ ] 第一个示例是最简调用（happy path）
- [ ] ENUMS 只列出高频枚举（值 ≤ 7 的选项）

## Help 检查

- [ ] OPTIONS 表每个字段含：名称、类型、必填、默认值、说明
- [ ] 枚举选项每个值有一句话说明
- [ ] 推荐值用 `[推荐]` 标注
- [ ] COMMON ERRORS 列出 3-5 个最高频错误
- [ ] COMMON EXAMPLES 含至少一个 `[PIPELINE]` 示例
- [ ] SEE ALSO 列出相关命令

## Sub-command Help 检查

- [ ] INHERITED OPTIONS 仅引用父命令，不重复列出
- [ ] 至少一个 `[TEMPLATE]` 示例
- [ ] 至少一个 `[RECOMMENDED]` 示例
- [ ] ERRORS 仅列出该子命令特有的错误

## Man 检查

- [ ] SCHEMA 区块使用 JSON Schema 格式
- [ ] 每个字段含 type + description + example
- [ ] EXIT CODES 完整列出
- [ ] ERRORS 含完整错误码清单（含 TRIGGER 和 RECOVERY）
- [ ] CAVEATS 列出已知限制
- [ ] COMPATIBILITY 记录 breaking changes（如有）

## Agent 友好性检查

- [ ] 所有区块使用大写标签（如 `OPTIONS:`）
- [ ] 无歧义代词（它、这个、上述）
- [ ] 互斥关系显式标注（在 Constraint 或说明中）
- [ ] 支持 `--schema` 输出 JSON Schema
- [ ] 支持 `--commands` 输出子命令列表
