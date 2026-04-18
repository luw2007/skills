#!/usr/bin/env python3
"""判定一次 skill 执行后是否值得启动深度分析。

用法:
    python should_improve.py <skill_dir> [--turns-threshold 20]
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
from pathlib import Path
from typing import Optional


DEFAULT_TURNS_THRESHOLD = 20


def load_feedback(skill_dir: Path) -> Optional[dict]:
    path = skill_dir.resolve() / "reports" / "feedback-log.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def should_improve(feedback: dict, turns_threshold: int = DEFAULT_TURNS_THRESHOLD) -> dict:
    """返回 {should: bool, reason: str}"""
    entries = feedback.get("entries", [])
    if not entries:
        return {"should": False, "reason": "无执行记录"}

    latest = entries[-1]
    category = latest.get("category", "general")
    turns = latest.get("turns", 0)
    rating = latest.get("rating", 3)

    # 规则 1: 错误或阻塞 → 必须分析
    if category in ("error", "blocking"):
        return {"should": True, "reason": f"最近执行类别为 {category}"}

    # 规则 2: 评分过低 → 分析
    if rating <= 2:
        return {"should": True, "reason": f"评分 {rating} <= 2，需分析"}

    # 规则 3: 成功但低效（轮数超阈值）
    if turns > turns_threshold:
        return {"should": True, "reason": f"轮数 {turns} > 阈值 {turns_threshold}，成功但低效"}

    # 规则 4: 近 5 次平均评分下滑
    recent = entries[-5:]
    ratings = [e["rating"] for e in recent if isinstance(e.get("rating"), int)]
    if len(ratings) >= 3:
        avg = sum(ratings) / len(ratings)
        if avg < 3.0:
            return {"should": True, "reason": f"近 {len(ratings)} 次平均评分 {avg:.1f} < 3.0"}

    return {"should": False, "reason": "执行正常，无需深度分析"}


def main() -> None:
    parser = argparse.ArgumentParser(description="判定是否需要触发改进分析")
    parser.add_argument("skill_dir", nargs="?", default=".")
    parser.add_argument("--turns-threshold", type=int, default=DEFAULT_TURNS_THRESHOLD)
    args = parser.parse_args()

    feedback = load_feedback(Path(args.skill_dir))
    if feedback is None:
        result = {"should": False, "reason": "未找到 feedback-log.json"}
    else:
        result = should_improve(feedback, args.turns_threshold)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
