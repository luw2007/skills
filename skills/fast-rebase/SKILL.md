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

4. **解决冲突。** 脚本在冲突处暂停。读冲突文件、理解两侧改动后**手术刀式**解决（常见形态与正解见 Local Lessons Learned），`git add` 后 `git rebase --continue`，直到完成。**冲突暂停后脚本已退出、自动校验不会跑——全部 continue 完成后必须手动跑一次 `--verify` 才能拿到逐字节铁证：**
   ```bash
   bash ~/.claude/skills/fast-rebase/scripts/fast-rebase.sh --verify
   ```

5. **验收。** 以脚本输出 `VERIFIED: ... byte-identical to <backup>` 为铁证——证明 rebase 后代码与备份逐字节一致、零丢失。若提示 tree differs，必须 `git diff <backup> HEAD` 核对差异来源（仅当 upstream 改过被保留文件时才允许非空）。

## 运行时自修复（L1）

git 行为与 squash MR body 格式会演化。执行中若某步与实际 git 输出不符（flag 变更、squash body 不再用 `* subject` 列表致 message 匹配失效、`git cherry` 格式变动），**就地修正 `scripts/fast-rebase.sh` 或判定逻辑并说明原因**，勿硬套过时步骤；并回灌到 Local Lessons Learned。

## 硬约束

- **禁止自动 push。** 完成后只告知备份分支名（`backup/pre-fast-rebase-*`），由用户自行删除。
- **保护未跟踪 WIP。** `--apply` 前工作树须干净（脚本会拒绝 dirty tree）；勿用 `reset --hard` 等会波及未提交文件的操作。
- **不重写无关历史。** 若要 drop 的 commit 被大量活跃 commit 压在历史中间，宁可放弃 drop 优化、用普通 rebase，也不为抹一个 commit 去 rebase 穿过他人在飞的工作。

## Local Lessons Learned

Private runtime lessons are stored outside Git so multiple local agents can share them without uploading them to GitHub.

- Read before execution: `${XDG_STATE_HOME:-~/.local/state}/openclaw-skills/fast-rebase/lessons-learned.md`
- If the file exists, treat it as part of this skill's local context.
- After real usage, update that file only when a new lesson changes future behavior.
- Keep at most 10 deduped lessons; evict stale or low-value entries first.
- When writing, acquire an atomic lock with `mkdir "${XDG_STATE_HOME:-$HOME/.local/state}/openclaw-skills/fast-rebase/lessons-learned.lock"`; remove it after the write.
- Do not commit the local lessons file or copy private lessons back into this `SKILL.md`.
