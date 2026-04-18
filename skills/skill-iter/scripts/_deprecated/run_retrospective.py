#!/usr/bin/env python3
"""端到端自迭代编排脚本。

串联 collect → should_improve → analyze → threat_scan → merge 形成完整闭环。
实现 D5（注入闭环）维度的自动化管线。

用法:
    # 完整管线：采集反馈 → 判定 → 分析 → 扫描 → 暂存经验
    python run_retrospective.py <skill_dir> --note "Phase 2 阻塞" --rating 2 --category blocking

    # 仅执行分析+合并（已有反馈数据时）
    python run_retrospective.py <skill_dir> --skip-collect

    # 自动确认合入（CI 场景）
    python run_retrospective.py <skill_dir> --note "正常" --auto-commit
"""
import warnings
warnings.warn(
    "此脚本已弃用，请使用 `skill-evolve` CLI。"
    " 参见 docs/2026-04-16-skill-evolve-engine-design.md 迁移计划。",
    DeprecationWarning,
    stacklevel=2,
)

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# 导入同目录下的工具脚本
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from collect_feedback import collect
from should_improve import load_feedback, should_improve
from analyze_trajectory import analyze_from_feedback
from threat_scan import scan_skill
from merge_lessons import pending_path, read_lessons, merge, write_lessons


def run_retrospective(
    skill_dir: Path,
    note: str | None = None,
    rating: int = 3,
    category: str = "general",
    turns: int = 0,
    session_id: str = "",
    skip_collect: bool = False,
    auto_commit: bool = False,
    turns_threshold: int = 20,
) -> dict:
    """执行完整的自迭代回顾管线"""
    skill_dir = skill_dir.resolve()
    pipeline_log = []
    timestamp = datetime.now().isoformat(timespec="seconds")

    # Step 1: 采集反馈
    if not skip_collect:
        collect_result = collect(skill_dir, note, rating, category, turns, session_id)
        pipeline_log.append({"step": "collect_feedback", "result": collect_result})
    else:
        pipeline_log.append({"step": "collect_feedback", "result": "skipped"})

    # Step 2: 触发判定
    feedback = load_feedback(skill_dir)
    if feedback is None:
        return {"ok": False, "reason": "无反馈数据", "pipeline_log": pipeline_log}

    verdict = should_improve(feedback, turns_threshold)
    pipeline_log.append({"step": "should_improve", "result": verdict})

    if not verdict["should"]:
        return {
            "ok": True,
            "action": "no_improvement_needed",
            "reason": verdict["reason"],
            "pipeline_log": pipeline_log,
        }

    # Step 3: 分析轨迹
    analysis = analyze_from_feedback(skill_dir, session_id if session_id else None)
    pipeline_log.append({"step": "analyze_trajectory", "result": analysis})

    if not analysis.get("ok"):
        return {"ok": False, "reason": "分析失败", "pipeline_log": pipeline_log}

    # Step 4: 提取 lesson 类建议
    lesson_suggestions = analysis.get("lesson_suggestions", [])
    if not lesson_suggestions:
        return {
            "ok": True,
            "action": "no_lessons_to_add",
            "reason": "分析完成但无需新增经验条目",
            "pipeline_log": pipeline_log,
        }

    # Step 5: 安全扫描（对建议文本做注入检测）
    scan_result = scan_skill(skill_dir)
    pipeline_log.append({"step": "threat_scan", "result": scan_result})

    if not scan_result["ok"]:
        return {
            "ok": False,
            "action": "threat_detected",
            "threats_found": scan_result["threats_found"],
            "reason": "安全扫描发现威胁，阻止自动合入",
            "pipeline_log": pipeline_log,
        }

    # Step 6: 写入 pending 或直接合入
    pending = pending_path(skill_dir)
    pending_items = json.loads(pending.read_text(encoding="utf-8")) if pending.exists() else []
    # 从建议中提取纯文本经验（去掉 [经验] 前缀）
    clean_lessons = []
    for s in lesson_suggestions:
        text = s
        for prefix in ("[固化] ", "[经验] ", "[忽略] "):
            if text.startswith(prefix):
                text = text[len(prefix):]
        clean_lessons.append(text)

    pending_items.extend(clean_lessons)
    pending.write_text(json.dumps(pending_items, ensure_ascii=False, indent=2), encoding="utf-8")
    pipeline_log.append({"step": "write_pending", "pending_count": len(pending_items)})

    if auto_commit:
        skill_md = skill_dir / "SKILL.md"
        existing = read_lessons(skill_md)
        merged = merge(existing, pending_items)
        write_lessons(skill_md, merged)
        pending.unlink()
        pipeline_log.append({"step": "auto_commit", "total_lessons": len(merged)})

        # 记录改进日志（D7 可观测性）
        _log_improvement(skill_dir, timestamp, session_id, lesson_suggestions, "auto_commit")

        return {
            "ok": True,
            "action": "auto_committed",
            "lessons_added": len(clean_lessons),
            "total_lessons": len(merged),
            "pipeline_log": pipeline_log,
        }

    # 记录改进日志
    _log_improvement(skill_dir, timestamp, session_id, lesson_suggestions, "pending")

    return {
        "ok": True,
        "action": "pending_review",
        "lessons_pending": len(clean_lessons),
        "hint": f"执行 `python scripts/merge_lessons.py {skill_dir} --commit` 确认合入",
        "pipeline_log": pipeline_log,
    }


def _log_improvement(skill_dir: Path, timestamp: str, session_id: str, suggestions: list, action: str) -> None:
    """记录改进日志到 reports/improvement-log.json（D7 可观测性）"""
    reports_dir = skill_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    log_path = reports_dir / "improvement-log.json"

    entries = []
    if log_path.exists():
        data = json.loads(log_path.read_text(encoding="utf-8"))
        entries = data.get("entries", [])

    entries.append({
        "timestamp": timestamp,
        "session_id": session_id,
        "action": action,
        "suggestions_count": len(suggestions),
        "suggestions": suggestions,
    })

    log_path.write_text(
        json.dumps({"entries": entries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="端到端自迭代编排管线")
    parser.add_argument("skill_dir", nargs="?", default=".")
    parser.add_argument("--note", help="本次执行备注")
    parser.add_argument("--rating", type=int, default=3)
    parser.add_argument("--category", default="general")
    parser.add_argument("--turns", type=int, default=0)
    parser.add_argument("--session-id", default="")
    parser.add_argument("--skip-collect", action="store_true", help="跳过反馈采集步骤")
    parser.add_argument("--auto-commit", action="store_true", help="自动确认合入（跳过人工审核）")
    parser.add_argument("--turns-threshold", type=int, default=20)
    args = parser.parse_args()

    result = run_retrospective(
        Path(args.skill_dir),
        note=args.note,
        rating=args.rating,
        category=args.category,
        turns=args.turns,
        session_id=args.session_id,
        skip_collect=args.skip_collect,
        auto_commit=args.auto_commit,
        turns_threshold=args.turns_threshold,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
