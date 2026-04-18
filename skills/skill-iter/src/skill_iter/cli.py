"""skill-iter CLI 入口。

子命令：
  audit   — D1-D7 审计
  evolve  — 从轨迹迭代
  pending — 候选管理（P2）
  watch   — 守护进程（P3）
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click

from skill_iter.adapters import load_adapter
from skill_iter.auditor import Auditor
from skill_iter.config import load_config


@click.group()
@click.version_option(package_name="skill-iter")
def main() -> None:
    """skill-iter: 单机本地优先的 Skill 迭代引擎"""


# ---------------------------------------------------------------------------
# audit 子命令
# ---------------------------------------------------------------------------
@main.command()
@click.argument("skill_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--json", "as_json", is_flag=True, help="JSON 格式输出")
@click.option("--ci", "ci_mode", is_flag=True, help="CI 模式：exit code 0=达标, 1=不达标")
def audit(skill_dir: Path, as_json: bool, ci_mode: bool) -> None:
    """对 SKILL.md 执行 D1-D7 自迭代能力审计。"""
    skill_dir = skill_dir.resolve()
    auditor = Auditor(skill_dir)
    report = auditor.audit()

    if as_json:
        click.echo(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        click.echo(report.to_table())
        # 如果有改进建议，输出
        suggestions = [
            (d.dimension, d.name, d.suggestions)
            for d in report.dimensions
            if d.suggestions
        ]
        if suggestions:
            click.echo("")
            click.echo("🔧 改进建议")
            click.echo("")
            for i, (dim, name, sugs) in enumerate(suggestions, 1):
                click.echo(f"{i}. [{dim}] {name}")
                for s in sugs:
                    click.echo(f"   - {s}")

    # adapter hook: 审计完成
    cfg = load_config(skill_dir)
    if cfg.adapter != "none":
        try:
            adapter = load_adapter(cfg.adapter, config={"skill_dir": str(skill_dir)})
            adapter.on_audit_complete(skill_dir, report.to_dict())
        except Exception as e:
            click.echo(f"⚠️  adapter 回调失败: {e}", err=True)

    if ci_mode:
        sys.exit(report.ci_exit_code())


# ---------------------------------------------------------------------------
# evolve 子命令 — 委托给 pipeline 模块
# ---------------------------------------------------------------------------
@main.command()
@click.argument("skill_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("-t", "--trajectory", "trajectory_path", type=click.Path(exists=True, path_type=Path), required=True)
@click.option("--format", "fmt", type=click.Choice(["auto", "md", "json", "jsonl"]), default="auto")
@click.option("--rating", type=int, default=None, help="手动提供评分（格式 C 无 result 时）")
@click.option("--model", default=None, help="覆盖 LLM 模型")
@click.option("--dry-run", is_flag=True, help="仅输出 patch，不写入 .pending_evolution/")
def evolve(
    skill_dir: Path,
    trajectory_path: Path,
    fmt: str,
    rating: int | None,
    model: str | None,
    dry_run: bool,
) -> None:
    """从 Agent 会话轨迹生成 SKILL.md 改进补丁。

    完整管线: 解析轨迹 → 触发判定 → 信号提取 → 门禁扫描 → 补丁生成 → 门禁验证 → 暂存
    """
    from skill_iter.pipeline import run_pipeline

    skill_dir = skill_dir.resolve()

    # 加载配置
    overrides: dict = {}
    if model:
        overrides["llm_model"] = model
    cfg = load_config(skill_dir, overrides)

    # 加载 adapter
    adapter = load_adapter(cfg.adapter, config={"skill_dir": str(skill_dir)})

    # 格式映射
    format_map = {"auto": "auto", "md": "A", "json": "B", "jsonl": "C"}
    parse_format = format_map.get(fmt, "auto")

    click.echo("📖 解析轨迹...", err=True)

    try:
        results = run_pipeline(
            skill_dir, trajectory_path, cfg,
            parse_format=parse_format,
            rating=rating,
            dry_run=dry_run,
            adapter=adapter,
        )
    except (ValueError, FileNotFoundError) as e:
        click.echo(f"❌ 轨迹解析失败: {e}", err=True)
        sys.exit(1)

    if not results:
        click.echo("❌ 未找到可解析的轨迹文件", err=True)
        sys.exit(1)

    # 输出各结果
    generated_count = 0
    for r in results:
        click.echo(f"\n{'='*60}", err=True)
        click.echo(f"📂 处理: {r.source}", err=True)
        if r.skip_reason:
            click.echo(f"⏭️  跳过: {r.skip_reason}", err=True)
        elif r.error:
            click.echo(f"❌ {r.error}", err=True)
        elif r.success:
            if r.patch_id:
                click.echo(f"✅ 已暂存: {r.patch_id}", err=True)
            else:
                click.echo("✅ 生成成功（dry-run 模式）", err=True)
            generated_count += 1

    # 汇总
    click.echo(f"\n{'='*60}", err=True)
    click.echo(f"处理完毕: {len(results)} 条轨迹，生成 {generated_count} 个候选补丁", err=True)
    if generated_count > 0 and not dry_run:
        click.echo(f"使用 `skill-iter pending list {skill_dir}` 查看候选补丁", err=True)


# ---------------------------------------------------------------------------
# pending 子命令组
# ---------------------------------------------------------------------------
@main.group()
def pending() -> None:
    """管理候选迭代补丁。"""


@pending.command("list")
@click.argument("skill_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
def pending_list(skill_dir: Path) -> None:
    """查看候选补丁列表。"""
    from skill_iter.pending_store import PendingStore

    store = PendingStore(skill_dir)
    patches = store.list()
    if not patches:
        click.echo("无候选补丁")
        return
    for p in patches:
        desc = p.description[:60] if p.description else ""
        created = p.created_at[:19] if p.created_at else ""
        click.echo(f"  {p.patch_id}  [{created}]  {desc}")


@pending.command("show")
@click.argument("patch_id")
@click.argument("skill_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
def pending_show(patch_id: str, skill_dir: Path) -> None:
    """查看补丁详情（含 diff 预览）。"""
    from skill_iter.pending_store import PendingStore, PatchNotFoundError

    store = PendingStore(skill_dir)
    try:
        patch = store.get(patch_id)
    except PatchNotFoundError as e:
        click.echo(str(e), err=True)
        sys.exit(1)

    click.echo(f"补丁 ID:    {patch.patch_id}")
    click.echo(f"创建时间:   {patch.created_at}")
    click.echo(f"来源轨迹:   {patch.source_trajectory}")
    click.echo(f"轨迹格式:   {patch.trajectory_format}")
    click.echo(f"base_hash:  {patch.base_hash[:16]}...")
    click.echo(f"门禁结果:   {patch.gate_result}")
    click.echo(f"说明:       {patch.description}")
    click.echo("")
    click.echo("--- diff 预览 ---")
    click.echo(patch.diff)
    if patch.new_content:
        click.echo("")
        click.echo("（全文替换模式，new_content 已就绪）")


@pending.command("commit")
@click.argument("patch_id")
@click.argument("skill_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
def pending_commit(patch_id: str, skill_dir: Path) -> None:
    """应用补丁到 SKILL.md（校验 base_hash 一致性）。"""
    from skill_iter.pending_store import (
        PendingStore,
        PatchNotFoundError,
        BaseHashMismatchError,
        PatchApplyError,
    )

    skill_dir = skill_dir.resolve()
    store = PendingStore(skill_dir)
    try:
        record = store.commit(patch_id)
    except PatchNotFoundError as e:
        click.echo(f"❌ {e}", err=True)
        sys.exit(1)
    except BaseHashMismatchError as e:
        click.echo(f"❌ {e}", err=True)
        sys.exit(1)
    except PatchApplyError as e:
        click.echo(f"❌ {e}", err=True)
        sys.exit(1)

    click.echo(f"✅ 已提交: {record.patch_id}")
    click.echo(f"   说明: {record.description}")
    click.echo(f"   备份: {record.backup_path}")
    click.echo(f"   新 hash: {record.new_hash[:16]}...")

    # adapter hook: 迭代合入
    cfg = load_config(skill_dir)
    if cfg.adapter != "none":
        try:
            adapter = load_adapter(cfg.adapter, config={"skill_dir": str(skill_dir)})
            adapter.on_evolution_committed(skill_dir, {
                "patch_id": record.patch_id,
                "description": record.description,
                "base_hash": record.base_hash,
                "new_hash": record.new_hash,
            })
        except Exception as e:
            click.echo(f"⚠️  adapter 回调失败: {e}", err=True)


@pending.command("discard")
@click.argument("patch_id")
@click.argument("skill_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--reason", default="", help="丢弃原因")
def pending_discard(patch_id: str, skill_dir: Path, reason: str) -> None:
    """丢弃补丁（记录日志）。"""
    from skill_iter.pending_store import PendingStore, PatchNotFoundError

    store = PendingStore(skill_dir)
    try:
        store.discard(patch_id, reason=reason)
    except PatchNotFoundError as e:
        click.echo(f"❌ {e}", err=True)
        sys.exit(1)
    click.echo(f"已丢弃: {patch_id}")


# ---------------------------------------------------------------------------
# watch 子命令 — P3 守护进程
# ---------------------------------------------------------------------------
@main.command()
@click.argument("skill_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--trajectory-dir", type=click.Path(exists=True, file_okay=False, path_type=Path), required=True)
@click.option("--model", default=None, help="覆盖 LLM 模型")
@click.option("--debounce", type=float, default=2.0, help="文件事件去抖延迟（秒）")
def watch(skill_dir: Path, trajectory_dir: Path, model: str | None, debounce: float) -> None:
    """监听轨迹目录，自动触发迭代管线（串行 FIFO）。"""
    from skill_iter.watcher import SkillWatcher

    skill_dir = skill_dir.resolve()
    trajectory_dir = Path(trajectory_dir).resolve()

    overrides: dict = {}
    if model:
        overrides["llm_model"] = model
    cfg = load_config(skill_dir, overrides)

    # 加载 adapter
    adapter = load_adapter(cfg.adapter, config={"skill_dir": str(skill_dir)})

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    watcher = SkillWatcher(
        skill_dir=skill_dir,
        trajectory_dir=trajectory_dir,
        config=cfg,
        debounce_seconds=debounce,
        adapter=adapter,
    )

    click.echo(f"👁️ 监听目录: {trajectory_dir}", err=True)
    click.echo(f"   Skill 目录: {skill_dir}", err=True)
    click.echo(f"   监听模式: {cfg.watch_patterns}", err=True)
    click.echo("   按 Ctrl+C 停止", err=True)

    try:
        watcher.start()
    except KeyboardInterrupt:
        pass
    finally:
        watcher.stop()
        click.echo("\n已停止监听", err=True)


if __name__ == "__main__":
    main()
