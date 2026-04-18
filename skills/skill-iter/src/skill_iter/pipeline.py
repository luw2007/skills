"""演化管线核心逻辑 — 供 evolve 命令和 watcher 共用。

管线: 解析轨迹 → 触发判定 → 信号提取 → 门禁扫描 → 补丁生成 → 门禁验证 → 暂存
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from skill_iter.adapters import AdapterInterface, load_adapter
from skill_iter.config import Config
from skill_iter.gateway import Gateway
from skill_iter.llm import LLMError, LLMParseError
from skill_iter.patch_generator import PatchGenerator
from skill_iter.signal_extractor import SignalExtractor
from skill_iter.trajectory import StructuredTrajectory, TrajectoryCollector
from skill_iter.trigger_judge import TriggerJudge

logger = logging.getLogger("skill-iter.pipeline")


@dataclass
class PipelineResult:
    """单条轨迹的管线执行结果。"""
    source: str
    success: bool
    patch_id: str | None = None
    skip_reason: str | None = None
    error: str | None = None


def load_feedback_history(skill_dir: Path) -> list[dict]:
    """加载 feedback-log.json 的 entries（用于 TriggerJudge 趋势分析）。"""
    path = skill_dir / "reports" / "feedback-log.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("entries", [])
    except (json.JSONDecodeError, OSError):
        return []


def save_pending(skill_dir: Path, patch, trajectory, cfg: Config) -> str:
    """将候选补丁写入 .pending_evolution/ 目录，返回 patch_id。"""
    pending_dir = skill_dir / cfg.pending_dir
    pending_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    content_hash = hashlib.sha256(patch.diff.encode()).hexdigest()[:8]
    patch_id = f"{ts}-{content_hash}"

    payload = {
        "patch_id": patch_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_trajectory": trajectory.source_path,
        "trajectory_format": trajectory.format,
        "description": patch.description,
        "diff": patch.diff,
        "new_content": patch.new_content,
        "base_hash": patch.base_hash,
        "signals_summary": patch.signals_summary,
        "gate_result": "passed",
    }

    path = pending_dir / f"{patch_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return patch_id


def log_error(skill_dir: Path, stage: str, source: str, detail) -> None:
    """记录演化错误到 reports/evolve-errors.json。"""
    reports_dir = skill_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    log_path = reports_dir / "evolve-errors.json"

    entries: list = []
    if log_path.exists():
        try:
            entries = json.loads(log_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            entries = []

    entries.append({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "stage": stage,
        "source": source,
        "detail": detail if isinstance(detail, (dict, list)) else str(detail),
    })

    # 保留最近 100 条
    entries = entries[-100:]
    log_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def run_single_trajectory(
    traj: StructuredTrajectory,
    skill_dir: Path,
    cfg: Config,
    *,
    feedback_history: list[dict] | None = None,
    dry_run: bool = False,
    adapter: AdapterInterface | None = None,
) -> PipelineResult:
    """对单条轨迹执行完整 7 步管线。

    返回 PipelineResult 说明成功/跳过/失败。
    此函数不做 click.echo，仅通过 logging 输出日志。
    adapter 参数可选，传入时在关键节点触发 hook 回调。
    """
    source = Path(traj.source_path).name
    if feedback_history is None:
        feedback_history = load_feedback_history(skill_dir)

    # 读取 SKILL.md
    skill_md_path = skill_dir / "SKILL.md"
    skill_md = skill_md_path.read_text(encoding="utf-8") if skill_md_path.exists() else ""

    # 初始化组件
    judge = TriggerJudge()
    extractor = SignalExtractor(
        model=cfg.llm_model,
        base_url=cfg.llm_base_url or None,
        max_trajectory_tokens=cfg.max_trajectory_tokens,
    )
    generator = PatchGenerator(model=cfg.llm_model, base_url=cfg.llm_base_url or None)
    gateway = Gateway(max_patch_lines=cfg.max_patch_lines)

    # 步骤 2: 触发判定
    trigger = judge.should_evolve(traj, feedback_history)
    if not trigger.should:
        logger.info("跳过 %s: %s", source, trigger.reason)
        return PipelineResult(source=source, success=False, skip_reason=trigger.reason)

    logger.info("触发演化 %s: %s", source, trigger.reason)

    # 步骤 3: 信号提取
    logger.info("提取信号 %s...", source)
    try:
        signals = extractor.extract(traj, skill_md)
    except (LLMError, LLMParseError) as e:
        log_error(skill_dir, "signal_extraction", source, str(e))
        if adapter:
            adapter.on_error("evolve", e)
        return PipelineResult(source=source, success=False, error=f"信号提取失败: {e}")

    signal_count = len(signals.invariants) + len(signals.fixes) + len(signals.new_phases)
    if signal_count == 0:
        return PipelineResult(source=source, success=False, skip_reason="无有效信号")

    # 步骤 4: 门禁扫描信号
    scan_result = gateway.scan_signals(signals)
    if not scan_result.ok:
        log_error(skill_dir, "signal_threat_scan", source, scan_result.to_dict())
        return PipelineResult(
            source=source, success=False,
            error=f"信号含 {scan_result.threats_found} 个威胁模式",
        )

    # 步骤 5: 补丁生成
    logger.info("生成补丁 %s...", source)
    try:
        patch = generator.generate(signals, skill_md)
    except LLMError as e:
        log_error(skill_dir, "patch_generation", source, str(e))
        if adapter:
            adapter.on_error("evolve", e)
        return PipelineResult(source=source, success=False, error=f"补丁生成失败: {e}")

    # 步骤 6: 门禁验证
    logger.info("门禁验证 %s...", source)
    gate_result = gateway.validate(patch, skill_md, skill_dir)

    if not gate_result.passed:
        # 尝试全文替换 fallback
        format_failed = any(c.name == "format_validation" for c in gate_result.failed_checks)
        if format_failed and patch.new_content is None:
            logger.info("尝试全文替换模式 %s...", source)
            try:
                patch = generator.generate_fulltext(signals, skill_md)
                gate_result = gateway.validate(patch, skill_md, skill_dir)
            except LLMError as e:
                log_error(skill_dir, "fulltext_generation", source, str(e))
                return PipelineResult(source=source, success=False, error=f"全文替换失败: {e}")

        if not gate_result.passed:
            reasons = "; ".join(f"{c.name}: {c.reason}" for c in gate_result.failed_checks)
            log_error(skill_dir, "gateway_validation", source, gate_result.to_dict())
            return PipelineResult(source=source, success=False, error=f"门禁未通过: {reasons}")

    # 步骤 7: 暂存
    if dry_run:
        logger.info("dry-run 模式，不暂存 %s", source)
        return PipelineResult(source=source, success=True)

    patch_id = save_pending(skill_dir, patch, traj, cfg)
    logger.info("已暂存 %s -> %s", source, patch_id)

    # adapter hook: 候选演化生成
    if adapter:
        adapter.on_evolution_proposed(skill_dir, {
            "patch_id": patch_id,
            "description": patch.description,
            "diff": patch.diff,
            "base_hash": patch.base_hash,
            "source": source,
        })

    return PipelineResult(source=source, success=True, patch_id=patch_id)


def run_pipeline(
    skill_dir: Path,
    trajectory_path: Path,
    cfg: Config,
    *,
    parse_format: str = "auto",
    rating: int | None = None,
    dry_run: bool = False,
    adapter: AdapterInterface | None = None,
) -> list[PipelineResult]:
    """解析轨迹并对每条轨迹执行管线。返回所有结果列表。"""
    collector = TrajectoryCollector()
    trajectory_path = trajectory_path.resolve()

    if trajectory_path.is_dir():
        trajectories = collector.parse_dir(trajectory_path, format=parse_format, rating=rating)
    elif trajectory_path.is_file():
        trajectories = [collector.parse(trajectory_path, format=parse_format, rating=rating)]
    else:
        return []

    if not trajectories:
        return []

    feedback_history = load_feedback_history(skill_dir)
    results: list[PipelineResult] = []

    for traj in trajectories:
        result = run_single_trajectory(
            traj, skill_dir, cfg,
            feedback_history=feedback_history,
            dry_run=dry_run,
            adapter=adapter,
        )
        results.append(result)

    return results
