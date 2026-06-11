# fast-rebase

> squash-merge 后的加速 rebase — 识别 upstream 已合并的本地 commit 并 drop，只重放未合并的，最后逐字节校验零代码丢失。

## 这是什么

长期分支被 squash-merge 进 `origin/master` 后再 rebase，git 会把那些**早已落地 upstream**的 commit 当作新工作重放，制造本可避免的冲突。fast-rebase 先做一次**只读判定**，把每个本地 commit 标成「已合并 / 待重放 / 需人工确认」，drop 掉已合并的，再用一个**确定性脚本**校验 rebase 结果与备份分支逐字节一致。

引擎是 `scripts/fast-rebase.sh`，零依赖（git + bash + awk/sed/perl，macOS / Linux 通用）。

## 为什么需要它

| 痛点 | fast-rebase 的解决方案 |
|------|----------------------|
| squash merge 后 `git cherry` 把所有本地 commit 标 `+`，patch-id 全失效，无法判断哪些已合并 | **三重信号三角定位**：commit MESSAGE + 作者 TIME + 改动文件 STATE 三者齐备才判已合并 |
| `git rebase` 在早已 landed 的工作上反复冲突 | 提前 drop 已合并 commit，只重放真正未合并的 |
| 不敢自动 rebase，怕丢代码 | rebase 前自动建 backup 分支，完成后 `git diff backup HEAD` 为空 = 逐字节零丢失的铁证 |
| 不确定本地哪些 commit 进了 upstream | 一条命令输出判定表，只读、不改任何东西 |

## 三重信号判定「同一份代码」

| 判定 | 含义 |
|------|------|
| **MERGED-EXACT** | `git cherry` patch-id 完全一致（cherry-pick / rebase 合并）→ drop |
| **MERGED-SQUASH** | commit subject 出现在某 upstream commit body 列表行 **+** authored 早于该 merge **+** 改的文件 ⊆ squash commit 改的文件 → drop |
| **REVIEW** | 仅 message 命中，时间或 state 不符 → 保留，需人工确认 |
| **UNMERGED** | upstream 无 → 保留重放 |

## 用法

```bash
# 1. 分析（只读，先 fetch 再判定）
bash scripts/fast-rebase.sh --fetch --base origin/master

# 2. 执行（自动建 backup、drop 已合并 commit、校验树一致）
bash scripts/fast-rebase.sh --base origin/master --apply

# 3. 若冲突暂停，手动解决后 git rebase --continue，全部完成再校验
bash scripts/fast-rebase.sh --verify
```

以脚本输出 `VERIFIED: HEAD is byte-identical to <backup>` 为验收铁证。

## 硬约束

- **禁止自动 push** — 完成后只告知备份分支名，由用户自行处理。
- **保护未提交 WIP** — `--apply` 前工作树须干净，脚本会拒绝 dirty tree。
- **不重写无关历史** — 待 drop 的 commit 若被大量他人在飞的 commit 压在中间，宁可退回普通 `git rebase`。

## 安装

```bash
npx skills add luw2007/skills --skill fast-rebase
# 或手动
cp -r skills/fast-rebase ~/.claude/skills/
```

## License

MIT
