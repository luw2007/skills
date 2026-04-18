#!/usr/bin/env python3
"""采集 skill 执行反馈，写入 reports/feedback-log.json。

用法:
    python collect_feedback.py <skill_dir> --note "首次执行，Phase 3 阻塞" --rating 2 --category blocking
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
from typing import List, Optional


def load_entries(path: Path) -> List[dict]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("entries", []) if isinstance(payload, dict) else []


def summarize(entries: list[dict]) -> dict:
    if not entries:
        return {"count": 0, "average_rating": 0, "error_count": 0, "blocked_count": 0}
    ratings = [e["rating"] for e in entries if isinstance(e.get("rating"), int)]
    return {
        "count": len(entries),
        "average_rating": round(sum(ratings) / len(ratings), 2) if ratings else 0,
        "error_count": sum(1 for e in entries if e.get("category") == "error"),
        "blocked_count": sum(1 for e in entries if e.get("category") == "blocking"),
    }


def collect(
    skill_dir: Path,
    note: str | None = None,
    rating: int = 3,
    category: str = "general",
    turns: int = 0,
    session_id: str = "",
) -> dict:
    skill_dir = skill_dir.resolve()
    reports_dir = skill_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    output = reports_dir / "feedback-log.json"

    entries = load_entries(output)
    if note:
        entries.append({
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "session_id": session_id,
            "category": category,
            "rating": max(1, min(rating, 5)),
            "turns": turns,
            "note": note,
        })

    payload = {"skill_dir": str(skill_dir), "entries": entries, "summary": summarize(entries)}
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "artifacts": {"json": str(output)}, "summary": payload["summary"]}


def main() -> None:
    parser = argparse.ArgumentParser(description="采集 skill 执行反馈")
    parser.add_argument("skill_dir", nargs="?", default=".")
    parser.add_argument("--note")
    parser.add_argument("--rating", type=int, default=3)
    parser.add_argument("--category", default="general")
    parser.add_argument("--turns", type=int, default=0)
    parser.add_argument("--session-id", default="")
    args = parser.parse_args()
    result = collect(Path(args.skill_dir), args.note, args.rating, args.category, args.turns, args.session_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
