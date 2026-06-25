---
name: worktree-cleanup
description: >-
  清理本地 git worktree：用 fast-rebase 判定 worktree commit 是否已合入 base（默认 master），
  只删除工作树干净且 commit 全部合入的工作副本，永不删分支/commit。Use when 用户要清理堆积
  worktree、判断哪些 worktree 可删、处理 squash 合并后的残留，或说 "worktree-cleanup"、
  "clean up worktrees"、"哪些 worktree 可以删"。
---

# worktree-cleanup

批量清理当前 git 仓库的 linked worktree：识别 commit 已全部合入 base 的 worktree 并
`git worktree remove` 其工作副本，**分支与 commit 永不删除**。判定引擎复用 fast-rebase
检测器（消息+时间+state 三重判定，能识破 squash 合并）。

脚本：`scripts/worktree-cleanup.sh`，**在目标 git 仓库内运行**。脚本默认查找同级
`fast-rebase/scripts/fast-rebase.sh` 或 PATH 中的 `fast-rebase.sh`；特殊安装位置用
`FR=/path/to/fast-rebase.sh` 覆盖。

## 仓库清单

本 skill 只处理当前 git 仓库。用 `git worktree list --porcelain` 固定本轮输入：
`worktree` 定位路径，`HEAD` 传给 fast-rebase，`branch` / `detached` 区分分支与游离 HEAD。
脏否由 `git -C <path> status --porcelain=v1` 判定；路径、base、引擎异常都 KEEP。

## 分桶判据

对每个非 main worktree 跑 `fast-rebase.sh --base <base> --head <HEAD>`（只读，不 checkout），
按 `to replay`（=UNMERGED+REVIEW 数）、工作树脏否、是否 detached 分桶：

- **REMOVE-SAFE** — 干净 + `to replay==0`（commit 全在 base）→ 可删
- **REMOVE-DIRTYWIP** — 已合入但有未提交改动 → 留（删需 --force，会丢 WIP）
- **KEEP-BRANCH-UNMERGED** — 命名分支 + 真未合入 commit → 留
- **KEEP-DETACHED-UNMERGED** — detached + 真未合入 → 留（删会变孤儿 commit）

## 工作流

1. **拉清单（只读）**：`git worktree list --porcelain > /tmp/worktree.porcelain`，固定本轮 review 的输入。
2. **分析（只读）**：`worktree-cleanup.sh --base master` → 打印各桶计数 + REMOVE-SAFE 候选清单；
   需要跨仓库清理时，进入每个仓库分别运行，不混合 apply。
3. **深度报告（可选）**：`worktree-cleanup.sh --base master --report <file>` → 三个 KEEP/DIRTY
   桶逐 worktree 的 commit 合入判定（哪些 MERGED 进 master、hash+subject）+ 未合入 commit 的文件
   范围 + 未提交改动，供用户逐个处理。
4. **决策（暂停）**：删除是破坏性操作——把 REMOVE-SAFE 候选呈现给用户确认后再执行。
5. **执行（仅确认后）**：无并发环境可用 `worktree-cleanup.sh --base master --apply`；并发环境必须把
   已确认的精确 `path` 写入 `/tmp/worktree-remove-safe.txt`，逐行 `git worktree remove "$path"`，最后
   `git worktree prune`。
6. **执行后回顾与触发判定（Post-run Phase）**：仅遇到 error、blocking、成功但低效（高轮次/重复人工判断）
   时才分析是否要改本 skill；按 codify / lesson / ignore 三分法处理。任何 skill 修改先给用户
   human review，不自动写入发布包；下次执行会自动包含本节和 Lessons Learned，形成
   `read SKILL.md → execute → review → write if approved` 闭环。

## 硬约束

- `git worktree remove` 只删工作副本，**分支与 commit 永不删**；已合并分支如需删除由用户另行
  `git branch -d <b>`（`-d` 会拒删未合并）。
- REMOVE-SAFE 必须干净；REMOVE-DIRTYWIP / KEEP-* 永不自动删。
- 跨仓库清理必须分仓库运行；不同 repo 的 worktree 不在同一次 apply 中混删。
- 引擎报 ERROR（输出不可识别）的 worktree 绝不当作 safe。
- base 默认本地 `master`（集成目标），离线判定不 fetch。master 只前进不回退时，已合入判定不失效。

## Do not use

- Do not use this skill to delete branches, tags, commits, remotes, or untracked repositories.
- Do not use `--apply` in concurrent agent/daemon environments unless removal is pinned to reviewed exact paths.
- Do not treat merge-base, merge-tree, branch name, statusline, or subject text alone as merged proof.

## 实战陷阱（务必遵守）

- **并发新建陷阱**：分析→apply 窗口期，并发 agent/daemon 会新建 worktree（如 `release-split-
  <date>/*`）甚至推进 `master`。并发环境必须「dry-run 出清单 → 人工 review → 按精确路径删」，
  绝不在 apply 阶段重新发现 REMOVE-SAFE。
- **merge-tree / merge-base 对 squash 失明**：别用 `git merge-tree --write-tree base <tip>`
  ==base树 或 `merge-base --is-ancestor` 当唯一「已合入」判据；squash 合并 + master 后续重构会误报。
  真要内容级加固，用净效果 patch-id：`patch-id(diff(merge-base..branch))` ==
  `patch-id(diff(squash^..squash))`，而非朴素 merge/diff。
- **subject 碰撞**：两个 worktree 同 commit subject 时 MERGED-SQUASH 可能误命中 → 误判已合入。
  当前「删 worktree 保留分支」已兜死此风险（commit 还在分支上）；**若要扩展脚本去自动删分支
  （更不可逆），必须先加上述 patch-id 内容证明做门禁**。

## Lessons Learned

- KEEP/REMOVE 判定只信 fast-rebase 输出和工作树脏否；展示字段、分支名、subject 都不能单独当证明。
- 并发环境必须按已 review 的精确路径删除；不要在 apply 阶段重新发现候选。
