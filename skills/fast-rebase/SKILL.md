---
name: fast-rebase
description: >-
  Accelerate rebasing a local branch onto an upstream that squash-merged some of its commits.
  Detects already-merged commits by triangulating three signals — commit MESSAGE, author TIME,
  and changed-file STATE — then drops them during an interactive rebase and verifies the result
  is byte-identical to a pre-rebase backup (zero code lost). Use when rebasing a long-lived local
  branch onto origin/master or origin/main where git would replay commits already squash-merged
  via an MR/PR, when `git rebase` hits avoidable conflicts on work already landed upstream, when
  you need to know which local commits are already in upstream, or when the user asks to
  "fast-rebase", "加速 rebase", "rebase 本地分支到 origin/master", clean up a branch after a squash
  merge, or identify which commits are 已合并 / 未合并.
---

# fast-rebase

固化 squash-merge 后的快速 rebase：识别 upstream 已合并的本地 commit 并 drop，只重放未合并的，最后校验代码逐字节零丢失。

引擎是确定性脚本 `scripts/fast-rebase.sh`（本机：`~/.claude/skills/fast-rebase/scripts/fast-rebase.sh`）。**在目标 git 仓库目录内运行。**

## 三重信号判定「同一份代码」

- **MERGED-EXACT** — `git cherry` patch-id 完全一致（cherry-pick / rebase 合并）。
- **MERGED-SQUASH** — commit subject 出现在某 upstream commit 的 body 列表行 + **时间**（authored 早于该 merge 的 commit time）+ **state**（它改的文件 ⊆ 该 squash commit 改的文件）三者齐备。
- **REVIEW** — 仅 message 命中，时间或 state 不符 → 保留，需人工确认。
- **UNMERGED** — upstream 无 → 保留重放。

## 工作流

1. **分析（只读，不改任何东西）。** 先 fetch 再判定，把判定表+drop plan 原样呈现：
   ```bash
   bash ~/.claude/skills/fast-rebase/scripts/fast-rebase.sh --fetch --base <base>
   ```
   `--base` 默认 `origin/master`；分析任意分支不 checkout 用 `--head <ref>`。

2. **决策。**
   - 输出 `0 already-merged` → 普通 `git rebase <base>` 即可，结束。
   - 出现 `REVIEW` 行 → **暂停**，逐条向用户解释 message 命中但时间/state 不符的原因，确认后再继续。
   - 用户未要求实际执行 → 停在分析，提示其确认后再加 `--apply`。

3. **执行（仅在用户确认/明确要求时）。** 脚本自动建 backup 分支、drop 已合并 commit、校验树一致：
   ```bash
   bash ~/.claude/skills/fast-rebase/scripts/fast-rebase.sh --base <base> --apply
   ```

4. **解决冲突。** 脚本在冲突处暂停。读冲突文件、理解两侧改动后**手术刀式**解决（常见形态与正解见 Lessons Learned），`git add` 后 `git rebase --continue`，直到完成。**冲突暂停后脚本已退出、自动校验不会跑——全部 continue 完成后必须手动跑一次 `--verify` 才能拿到逐字节铁证：**
   ```bash
   bash ~/.claude/skills/fast-rebase/scripts/fast-rebase.sh --verify
   ```

5. **验收。** 以脚本输出 `VERIFIED: ... byte-identical to <backup>` 为铁证——证明 rebase 后代码与备份逐字节一致、零丢失。若提示 tree differs，必须 `git diff <backup> HEAD` 核对差异来源（仅当 upstream 改过被保留文件时才允许非空）。

## 运行时自修复（L1）

git 行为与 squash MR body 格式会演化。执行中若某步与实际 git 输出不符（flag 变更、squash body 不再用 `* subject` 列表致 message 匹配失效、`git cherry` 格式变动），**就地修正 `scripts/fast-rebase.sh` 或判定逻辑并说明原因**，勿硬套过时步骤；并回灌到下方 Lessons Learned。

## 硬约束

- **禁止自动 push。** 完成后只告知备份分支名（`backup/pre-fast-rebase-*`），由用户自行删除。
- **保护未跟踪 WIP。** `--apply` 前工作树须干净（脚本会拒绝 dirty tree）；勿用 `reset --hard` 等会波及未提交文件的操作。
- **不重写无关历史。** 若要 drop 的 commit 被大量活跃 commit 压在历史中间，宁可放弃 drop 优化、用普通 rebase，也不为抹一个 commit 去 rebase 穿过他人在飞的工作。

## Lessons Learned

> 每次实战后把新教训追加到此（去重，约 10 条上限，超出汰旧）。下次加载本 skill 时自动读到。

- **patch-id 在 squash 下必然失效**：squash merge 后 `git cherry` 会把所有本地 commit 标 `+`——多个 commit 被压成一个、patch-id 全对不上。这正是必须用 message+time+state、而非单纯 `git cherry` 的根本原因。
- **冲突最常见形态 = 同位置双新增**：squash 把后续 commit 的改动并入了 base，重放靠前 commit 时，常见「双方各新增一个独立函数落在同一处」。正解是**两个都保留**（别二选一）；务必检查被保留函数的调用点是否已在同提交其他 hunk 出现，以及两侧是否共用了冲突标记后的同一个尾括号。
- **验证黄金法则**：`--apply` 后 `git diff <backup> HEAD` 为空 = 改动集等价、逐字节零丢失——比「测试通过」更硬，直接证明树相等。
- **upstream-only ≠ 已合并**：upstream 多出的 commit 若三重比对均不命中本地 subject，它是 upstream 的独立新工作，不可当作本地 commit 的合并体而 drop。
