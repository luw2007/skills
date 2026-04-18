#!/usr/bin/env python3
"""将新的经验条目合并到 SKILL.md 的 Lessons Learned 章节。

支持去重 + FIFO 淘汰。新条目先写入 .pending 文件，需人工确认后合入。

用法:
    # 写入 pending
    python merge_lessons.py <skill_dir> --add "避免在 Phase 2 使用 glob 匹配大仓"
    # 确认 pending 合入
    python merge_lessons.py <skill_dir> --commit
    # 查看当前经验列表
    python merge_lessons.py <skill_dir> --list
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
import re
from pathlib import Path
from typing import List

MAX_ENTRIES = 10
LESSONS_HEADER = "## Lessons Learned"
LESSONS_PATTERN = re.compile(r"^## Lessons?\s+Learned", re.IGNORECASE | re.MULTILINE)


def read_lessons(skill_md: Path) -> list[str]:
    """从 SKILL.md 提取 Lessons Learned 章节中的条目"""
    if not skill_md.exists():
        return []
    text = skill_md.read_text(encoding="utf-8")
    match = LESSONS_PATTERN.search(text)
    if not match:
        return []
    start = match.end()
    # 找到下一个 ## 标题或文件末尾
    next_header = re.search(r"^## ", text[start:], re.MULTILINE)
    section = text[start:start + next_header.start()] if next_header else text[start:]
    items = []
    for line in section.strip().splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            items.append(stripped[2:].strip())
    return items


def write_lessons(skill_md: Path, items: list[str]) -> None:
    """将经验列表写回 SKILL.md 的 Lessons Learned 章节"""
    text = skill_md.read_text(encoding="utf-8")
    bullet_block = "\n".join(f"- {item}" for item in items)
    new_section = f"{LESSONS_HEADER}\n\n{bullet_block}\n"

    match = LESSONS_PATTERN.search(text)
    if match:
        start = match.start()
        next_header = re.search(r"^## ", text[match.end():], re.MULTILINE)
        end = match.end() + next_header.start() if next_header else len(text)
        text = text[:start] + new_section + "\n" + text[end:]
    else:
        text = text.rstrip() + "\n\n" + new_section
    skill_md.write_text(text, encoding="utf-8")


def merge(existing: list[str], new_items: list[str], max_entries: int = MAX_ENTRIES) -> list[str]:
    """去重合并 + FIFO 淘汰"""
    seen = {item.strip().lower() for item in existing}
    merged = list(existing)
    for item in new_items:
        if item.strip().lower() not in seen:
            merged.append(item)
            seen.add(item.strip().lower())
    return merged[-max_entries:]


def pending_path(skill_dir: Path) -> Path:
    return skill_dir / ".pending_lessons.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="管理 SKILL.md 的 Lessons Learned 章节")
    parser.add_argument("skill_dir", nargs="?", default=".")
    parser.add_argument("--add", help="添加一条经验到 .pending 文件")
    parser.add_argument("--commit", action="store_true", help="将 .pending 中的经验合入 SKILL.md")
    parser.add_argument("--list", action="store_true", help="列出当前经验")
    parser.add_argument("--max-entries", type=int, default=MAX_ENTRIES)
    args = parser.parse_args()

    skill_dir = Path(args.skill_dir).resolve()
    skill_md = skill_dir / "SKILL.md"
    pending = pending_path(skill_dir)

    if args.add:
        items = json.loads(pending.read_text(encoding="utf-8")) if pending.exists() else []
        items.append(args.add)
        pending.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"ok": True, "action": "pending", "pending_count": len(items)}))

    elif args.commit:
        if not pending.exists():
            print(json.dumps({"ok": False, "reason": "无 pending 经验"}))
            return
        new_items = json.loads(pending.read_text(encoding="utf-8"))
        existing = read_lessons(skill_md)
        merged = merge(existing, new_items, args.max_entries)
        write_lessons(skill_md, merged)
        pending.unlink()
        print(json.dumps({"ok": True, "action": "committed", "total": len(merged)}))

    elif args.list:
        items = read_lessons(skill_md)
        pending_items = json.loads(pending.read_text(encoding="utf-8")) if pending.exists() else []
        print(json.dumps({"committed": items, "pending": pending_items}, ensure_ascii=False, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
