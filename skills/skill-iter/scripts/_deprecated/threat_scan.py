#!/usr/bin/env python3
"""检测 SKILL.md 或经验条目中的 prompt 注入威胁。

用法:
    python threat_scan.py <skill_dir>
    python threat_scan.py --text "ignore all previous instructions"
"""
import warnings
warnings.warn(
    "此脚本已弃用，请使用 `skill-evolve` CLI。"
    " 参见 docs/2026-04-16-skill-evolve-engine-design.md 迁移计划。",
    DeprecationWarning,
    stacklevel=2,
)

import argparse
import json
import re
from pathlib import Path

THREAT_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),
    re.compile(r"system\s+prompt\s*:", re.IGNORECASE),
    re.compile(r"<\s*/?system\s*>", re.IGNORECASE),
    re.compile(r"IMPORTANT:\s*NEW\s+INSTRUCTIONS", re.IGNORECASE),
    re.compile(r"[\u200b\u200c\u200d\u200e\u200f]"),  # 隐形 unicode
    re.compile(r"act\s+as\s+(if\s+)?you\s+(are|were)\s+", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(prior|above|previous)", re.IGNORECASE),
]


def scan_text(text: str) -> list[dict]:
    threats = []
    for i, pattern in enumerate(THREAT_PATTERNS):
        for match in pattern.finditer(text):
            threats.append({
                "pattern_index": i,
                "pattern": pattern.pattern,
                "match": match.group(),
                "position": match.start(),
            })
    return threats


def scan_skill(skill_dir: Path) -> dict:
    skill_dir = skill_dir.resolve()
    all_threats = []

    # 扫描 SKILL.md
    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists():
        threats = scan_text(skill_md.read_text(encoding="utf-8"))
        for t in threats:
            t["file"] = "SKILL.md"
        all_threats.extend(threats)

    # 扫描 .pending_lessons.json
    pending = skill_dir / ".pending_lessons.json"
    if pending.exists():
        text = pending.read_text(encoding="utf-8")
        threats = scan_text(text)
        for t in threats:
            t["file"] = ".pending_lessons.json"
        all_threats.extend(threats)

    # 扫描 reports/feedback-log.json 中的 note 字段
    feedback = skill_dir / "reports" / "feedback-log.json"
    if feedback.exists():
        data = json.loads(feedback.read_text(encoding="utf-8"))
        for entry in data.get("entries", []):
            note = entry.get("note", "")
            threats = scan_text(note)
            for t in threats:
                t["file"] = f"feedback-log.json[{entry.get('session_id', '?')}]"
            all_threats.extend(threats)

    return {
        "ok": len(all_threats) == 0,
        "threats_found": len(all_threats),
        "threats": all_threats,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Prompt 注入威胁扫描")
    parser.add_argument("skill_dir", nargs="?", default=".")
    parser.add_argument("--text", help="直接扫描指定文本")
    args = parser.parse_args()

    if args.text:
        threats = scan_text(args.text)
        print(json.dumps({"ok": len(threats) == 0, "threats": threats}, ensure_ascii=False, indent=2))
    else:
        result = scan_skill(Path(args.skill_dir))
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
