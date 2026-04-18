#!/usr/bin/env python3
"""从执行反馈中提取结构化改进条目。

实现 SKILL.md D3 维度的三分法分析：
- 固化为工具调用 → 确定性步骤，建议写入 SKILL.md Phase
- 记录为经验规避 → 条件性步骤，建议写入 Lessons Learned
- 无需处理 → 一次性问题，仅记录在报告中

用法:
    python analyze_trajectory.py <skill_dir> [--session-id SESSION]
    python analyze_trajectory.py <skill_dir> --from-feedback
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
from datetime import datetime
from pathlib import Path
from typing import Optional


# 改进条目分类
CATEGORY_CODIFY = "codify"       # 固化为工具调用/Phase 步骤
CATEGORY_LESSON = "lesson"       # 记录为经验规避
CATEGORY_IGNORE = "ignore"       # 无需处理

# 基于反馈类别和评分的分类启发式规则
CATEGORY_RULES = {
    "blocking": CATEGORY_CODIFY,   # 阻塞问题 → 固化步骤以永久避免
    "error": CATEGORY_LESSON,      # 错误 → 记录经验以供参考
    "general": CATEGORY_IGNORE,    # 一般反馈 → 无需特殊处理
}


def classify_feedback_entry(entry: dict) -> dict:
    """将单条反馈分类为三分法中的一类，并生成改进条目"""
    category = entry.get("category", "general")
    rating = entry.get("rating", 3)
    note = entry.get("note", "")
    turns = entry.get("turns", 0)

    # 基于反馈类别的初始分类
    improvement_type = CATEGORY_RULES.get(category, CATEGORY_IGNORE)

    # 评分修正：低评分但非 blocking → 提升为 lesson
    if rating <= 2 and improvement_type == CATEGORY_IGNORE:
        improvement_type = CATEGORY_LESSON

    # 高轮数修正：成功但低效 → 提升为 lesson
    if turns > 20 and improvement_type == CATEGORY_IGNORE:
        improvement_type = CATEGORY_LESSON

    # 生成改进建议文本
    suggestion = _generate_suggestion(improvement_type, entry)

    return {
        "type": improvement_type,
        "source_session": entry.get("session_id", ""),
        "source_category": category,
        "rating": rating,
        "turns": turns,
        "suggestion": suggestion,
        "original_note": note,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }


def _generate_suggestion(improvement_type: str, entry: dict) -> str:
    """根据分类类型和反馈内容生成改进建议"""
    note = entry.get("note", "（无备注）")
    category = entry.get("category", "general")

    if improvement_type == CATEGORY_CODIFY:
        return f"[固化] 阻塞问题需写入 SKILL.md 为确定性步骤：{note}"
    elif improvement_type == CATEGORY_LESSON:
        if entry.get("rating", 3) <= 2:
            return f"[经验] 低评分执行（{category}），建议记录为 Lessons Learned：{note}"
        elif entry.get("turns", 0) > 20:
            return f"[经验] 执行轮数过高（{entry['turns']}轮），建议优化流程：{note}"
        return f"[经验] 条件性问题，建议记录为 Lessons Learned：{note}"
    else:
        return f"[忽略] 一次性问题，仅记录：{note}"


def analyze_from_feedback(skill_dir: Path, session_id: str | None = None) -> dict:
    """从 feedback-log.json 分析反馈并生成改进条目"""
    feedback_path = skill_dir.resolve() / "reports" / "feedback-log.json"
    if not feedback_path.exists():
        return {"ok": False, "reason": "未找到 reports/feedback-log.json"}

    data = json.loads(feedback_path.read_text(encoding="utf-8"))
    entries = data.get("entries", [])

    if session_id:
        entries = [e for e in entries if e.get("session_id") == session_id]

    if not entries:
        return {"ok": True, "items": [], "reason": "无匹配的反馈条目"}

    items = [classify_feedback_entry(e) for e in entries]

    # 按类型汇总
    summary = {
        CATEGORY_CODIFY: [i for i in items if i["type"] == CATEGORY_CODIFY],
        CATEGORY_LESSON: [i for i in items if i["type"] == CATEGORY_LESSON],
        CATEGORY_IGNORE: [i for i in items if i["type"] == CATEGORY_IGNORE],
    }

    # 写入分析报告
    reports_dir = skill_dir.resolve() / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / "analysis-report.json"
    report = {
        "analyzed_at": datetime.now().isoformat(timespec="seconds"),
        "session_filter": session_id,
        "total_entries": len(entries),
        "codify_count": len(summary[CATEGORY_CODIFY]),
        "lesson_count": len(summary[CATEGORY_LESSON]),
        "ignore_count": len(summary[CATEGORY_IGNORE]),
        "items": items,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "ok": True,
        "artifacts": {"json": str(report_path)},
        "codify_count": report["codify_count"],
        "lesson_count": report["lesson_count"],
        "ignore_count": report["ignore_count"],
        "lesson_suggestions": [i["suggestion"] for i in summary[CATEGORY_LESSON]],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="从执行反馈中提取结构化改进条目（三分法）")
    parser.add_argument("skill_dir", nargs="?", default=".")
    parser.add_argument("--session-id", help="仅分析指定 session 的反馈")
    parser.add_argument("--from-feedback", action="store_true", help="从 feedback-log.json 分析")
    args = parser.parse_args()

    result = analyze_from_feedback(Path(args.skill_dir), args.session_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
