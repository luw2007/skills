"""安全扫描模块 — 检测 SKILL.md / 经验条目中的 prompt 注入威胁。

从 scripts/threat_scan.py 迁移并扩展，提供面向模块的 API。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

# ---------------------------------------------------------------------------
# 威胁模式定义
# ---------------------------------------------------------------------------
# 每个条目: (名称, 正则模式, flags)
_PATTERN_DEFS: list[tuple[str, str, int]] = [
    # ---- 原有 8 个模式 ----
    (
        "ignore_previous_instructions",
        r"ignore\s+(all\s+)?previous\s+instructions",
        re.IGNORECASE,
    ),
    (
        "role_hijack_you_are_now",
        r"you\s+are\s+now\s+",
        re.IGNORECASE,
    ),
    (
        "system_prompt_label",
        r"system\s+prompt\s*:",
        re.IGNORECASE,
    ),
    (
        "fake_system_tag",
        r"<\s*/?system\s*>",
        re.IGNORECASE,
    ),
    (
        "important_new_instructions",
        r"IMPORTANT:\s*NEW\s+INSTRUCTIONS",
        re.IGNORECASE,
    ),
    (
        "invisible_unicode",
        r"[\u200b\u200c\u200d\u200e\u200f]",
        0,
    ),
    (
        "act_as_roleplay",
        r"act\s+as\s+(if\s+)?you\s+(are|were)\s+",
        re.IGNORECASE,
    ),
    (
        "disregard_prior",
        r"disregard\s+(all\s+)?(prior|above|previous)",
        re.IGNORECASE,
    ),
    # ---- 扩展模式 ----
    (
        "base64_encoded_instruction",
        r"(?:execute|run|decode|eval)\s+(?:the\s+)?base64[\s:]+[A-Za-z0-9+/=]{20,}",
        re.IGNORECASE,
    ),
    (
        "base64_inline_block",
        r"[A-Za-z0-9+/]{40,}={0,2}",
        0,
    ),
    (
        "markdown_link_injection",
        r"!\[[^\]]*\]\(https?://[^)]+\)",
        0,
    ),
    (
        "markdown_reference_exfil",
        r"\[[^\]]*\]\(data:[^)]+\)",
        0,
    ),
    (
        "hidden_html_comment",
        r"<!--[\s\S]*?-->",
        0,
    ),
    (
        "do_not_mention",
        r"do\s+not\s+(mention|reveal|disclose|tell)",
        re.IGNORECASE,
    ),
    (
        "forget_everything",
        r"forget\s+(everything|all|prior|previous)",
        re.IGNORECASE,
    ),
    (
        "override_instructions",
        r"override\s+(your\s+)?(instructions|rules|guidelines|system\s+prompt)",
        re.IGNORECASE,
    ),
    (
        "new_persona",
        r"(from\s+now\s+on|henceforth)\s+you\s+(are|will|should|must)",
        re.IGNORECASE,
    ),
    (
        "jailbreak_dan",
        r"\bDAN\b.*\b(do\s+anything|jailbreak)",
        re.IGNORECASE,
    ),
    (
        "prompt_leak_request",
        r"(show|print|output|repeat|reveal)\s+(your\s+)?(system\s+prompt|instructions|initial\s+prompt)",
        re.IGNORECASE,
    ),
    (
        "data_exfiltration_url",
        r"https?://[^\s)\"'>]+\{\{.*?\}\}",
        0,
    ),
]

# 编译后的命名模式列表
THREAT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (name, re.compile(pattern, flags))
    for name, pattern, flags in _PATTERN_DEFS
]


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
@dataclass
class ThreatMatch:
    pattern_name: str
    pattern: str
    matched_text: str
    position: int
    file: str | None = None


@dataclass
class ScanResult:
    ok: bool
    threats_found: int
    threats: list[ThreatMatch] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "threats_found": self.threats_found,
            "threats": [asdict(t) for t in self.threats],
        }


# ---------------------------------------------------------------------------
# 扫描 API
# ---------------------------------------------------------------------------
def scan_text(text: str) -> list[ThreatMatch]:
    """扫描文本，返回匹配到的威胁列表。"""
    threats: list[ThreatMatch] = []
    for name, compiled in THREAT_PATTERNS:
        for match in compiled.finditer(text):
            threats.append(ThreatMatch(
                pattern_name=name,
                pattern=compiled.pattern,
                matched_text=match.group(),
                position=match.start(),
            ))
    return threats


def scan_file(path: Path) -> list[ThreatMatch]:
    """扫描单个文件，返回匹配到的威胁列表。"""
    path = Path(path).resolve()
    text = path.read_text(encoding="utf-8")
    threats = scan_text(text)
    for t in threats:
        t.file = str(path.name)
    return threats


def _scan_json_file(path: Path, label: str | None = None) -> list[ThreatMatch]:
    """扫描 JSON 文件的全部文本内容。"""
    text = path.read_text(encoding="utf-8")
    threats = scan_text(text)
    file_label = label or path.name
    for t in threats:
        t.file = file_label
    return threats


def _scan_feedback_notes(path: Path) -> list[ThreatMatch]:
    """扫描 feedback-log.json 等文件中的 note 字段。"""
    threats: list[ThreatMatch] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return threats
    entries = data.get("entries", []) if isinstance(data, dict) else []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        note = entry.get("note", "")
        if not note:
            continue
        found = scan_text(note)
        session_id = entry.get("session_id", "?")
        for t in found:
            t.file = f"{path.name}[{session_id}]"
        threats.extend(found)
    return threats


def scan_skill_dir(skill_dir: Path) -> ScanResult:
    """扫描 skill 目录下所有相关文件。

    扫描范围:
    - SKILL.md
    - .pending_evolution/ 下所有 .json 文件
    - .pending_lessons.json（兼容旧格式）
    - reports/ 下 JSON 文件的 note 字段
    """
    skill_dir = Path(skill_dir).resolve()
    all_threats: list[ThreatMatch] = []

    # 1) SKILL.md
    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists():
        all_threats.extend(scan_file(skill_md))

    # 2) .pending_evolution/ 目录下所有 json
    pending_dir = skill_dir / ".pending_evolution"
    if pending_dir.is_dir():
        for json_file in sorted(pending_dir.glob("*.json")):
            found = _scan_json_file(json_file, f".pending_evolution/{json_file.name}")
            all_threats.extend(found)

    # 3) .pending_lessons.json（旧格式兼容）
    pending_legacy = skill_dir / ".pending_lessons.json"
    if pending_legacy.exists():
        found = _scan_json_file(pending_legacy)
        all_threats.extend(found)

    # 4) reports/ 下的 JSON 文件 — 扫描 note 字段
    reports_dir = skill_dir / "reports"
    if reports_dir.is_dir():
        for json_file in sorted(reports_dir.glob("*.json")):
            all_threats.extend(_scan_feedback_notes(json_file))

    return ScanResult(
        ok=len(all_threats) == 0,
        threats_found=len(all_threats),
        threats=all_threats,
    )
