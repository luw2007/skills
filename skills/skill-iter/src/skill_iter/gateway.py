"""质量门禁模块 — 候选 patch 必须通过 4 条检查才能进入 .pending_evolution/。

门禁规则：
1. D6 threat_scan: patch 内容 + 信号中间产物不含 prompt 注入模式
2. 格式校验: patch 应用后的 SKILL.md 仍是合法 Markdown
3. D1-D7 非降级: 应用 patch 后各维度评分不低于应用前
4. diff 大小限制: 单次 patch 变更行数 ≤ max_patch_lines
"""
from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from skill_iter.auditor import Auditor, Grade, AuditReport
from skill_iter.patch_generator import Patch
from skill_iter.signal_extractor import Signals
from skill_iter.threat_scan import scan_text, ScanResult


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

_GRADE_ORDER = {
    Grade.MISSING: 0,
    Grade.BASIC: 1,
    Grade.GOOD: 2,
    Grade.EXCELLENT: 3,
}


@dataclass
class GateResult:
    """门禁检查结果。"""
    passed: bool
    checks: list[CheckDetail] = field(default_factory=list)

    @property
    def failed_checks(self) -> list[CheckDetail]:
        return [c for c in self.checks if not c.passed]

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "checks": [
                {"name": c.name, "passed": c.passed, "reason": c.reason}
                for c in self.checks
            ],
        }


@dataclass
class CheckDetail:
    """单项检查详情。"""
    name: str
    passed: bool
    reason: str


# ---------------------------------------------------------------------------
# 门禁引擎
# ---------------------------------------------------------------------------

class Gateway:
    """质量门禁，对候选 patch 执行 4 条检查。"""

    def __init__(self, max_patch_lines: int = 50) -> None:
        self.max_patch_lines = max_patch_lines

    def scan_signals(self, signals: Signals) -> ScanResult:
        """对信号提取的中间产物进行 threat_scan。

        在 PatchGenerator 之前调用，拦截含注入模式的信号。
        """
        # 将信号序列化为文本进行扫描
        text = json.dumps(signals.raw_response, ensure_ascii=False)
        threats = scan_text(text)
        return ScanResult(
            ok=len(threats) == 0,
            threats_found=len(threats),
            threats=threats,
        )

    def validate(self, patch: Patch, skill_md: str, skill_dir: Path) -> GateResult:
        """对候选 patch 执行全部门禁检查。

        Args:
            patch: 待验证的补丁
            skill_md: 当前 SKILL.md 全文
            skill_dir: Skill 目录路径（用于 Auditor 实例化）

        Returns:
            GateResult 对象
        """
        checks: list[CheckDetail] = []

        # 规则 1: D6 threat_scan — patch 内容扫描
        checks.append(self._check_threat_scan(patch))

        # 规则 2: 格式校验 — 应用 patch 后仍是合法 Markdown
        new_content, fmt_check = self._check_format(patch, skill_md)
        checks.append(fmt_check)

        # 规则 3: D1-D7 非降级
        if new_content is not None:
            checks.append(self._check_non_degradation(new_content, skill_dir))
        else:
            checks.append(CheckDetail(
                name="d1_d7_non_degradation",
                passed=False,
                reason="无法应用 patch，跳过非降级检查",
            ))

        # 规则 4: diff 大小限制
        checks.append(self._check_diff_size(patch))

        passed = all(c.passed for c in checks)
        return GateResult(passed=passed, checks=checks)

    # ------ 规则 1: threat_scan ------

    @staticmethod
    def _check_threat_scan(patch: Patch) -> CheckDetail:
        """扫描 patch diff 和 description 中的威胁模式。"""
        threats = scan_text(patch.diff)
        threats.extend(scan_text(patch.description))
        if patch.new_content:
            threats.extend(scan_text(patch.new_content))

        if not threats:
            return CheckDetail(
                name="threat_scan",
                passed=True,
                reason="patch 内容未检测到 prompt 注入模式",
            )
        names = list({t.pattern_name for t in threats})
        return CheckDetail(
            name="threat_scan",
            passed=False,
            reason=f"检测到 {len(threats)} 个威胁模式: {', '.join(names[:5])}",
        )

    # ------ 规则 2: 格式校验 ------

    @staticmethod
    def _check_format(patch: Patch, skill_md: str) -> tuple[str | None, CheckDetail]:
        """检查 patch 应用后的 SKILL.md 是否为合法 Markdown。

        Returns:
            (new_content, check_detail)，new_content 为应用后的内容（None 表示 apply 失败）
        """
        new_content = _apply_patch(patch, skill_md)

        if new_content is None:
            return None, CheckDetail(
                name="format_validation",
                passed=False,
                reason="无法应用 patch 到当前 SKILL.md",
            )

        # Markdown 合法性：非空 + 包含至少一个标题
        if not new_content.strip():
            return None, CheckDetail(
                name="format_validation",
                passed=False,
                reason="应用 patch 后 SKILL.md 为空",
            )

        # 基础 Markdown 校验：应包含至少一个 # 标题
        has_heading = any(
            line.strip().startswith("#")
            for line in new_content.splitlines()
        )
        if not has_heading:
            return new_content, CheckDetail(
                name="format_validation",
                passed=False,
                reason="应用 patch 后 SKILL.md 不含任何 Markdown 标题",
            )

        return new_content, CheckDetail(
            name="format_validation",
            passed=True,
            reason="应用 patch 后 SKILL.md 格式合法",
        )

    # ------ 规则 3: D1-D7 非降级 ------

    @staticmethod
    def _check_non_degradation(new_content: str, skill_dir: Path) -> CheckDetail:
        """比较 patch 前后的 D1-D7 评分，不允许降级。"""
        # 审计前
        auditor_before = Auditor(skill_dir)
        report_before = auditor_before.audit()

        # 审计后：写入临时目录
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            # 复制必要文件
            _mirror_skill_dir(skill_dir, tmp_dir)
            # 写入新 SKILL.md
            (tmp_dir / "SKILL.md").write_text(new_content, encoding="utf-8")
            auditor_after = Auditor(tmp_dir)
            report_after = auditor_after.audit()

        # 比较各维度
        degraded: list[str] = []
        for before, after in zip(report_before.dimensions, report_after.dimensions):
            grade_before = _GRADE_ORDER[before.grade]
            grade_after = _GRADE_ORDER[after.grade]
            if grade_after < grade_before:
                degraded.append(
                    f"{before.dimension}({before.grade.value}→{after.grade.value})"
                )

        if not degraded:
            return CheckDetail(
                name="d1_d7_non_degradation",
                passed=True,
                reason="所有维度评分未降级",
            )
        return CheckDetail(
            name="d1_d7_non_degradation",
            passed=False,
            reason=f"以下维度降级: {', '.join(degraded)}",
        )

    # ------ 规则 4: diff 大小限制 ------

    def _check_diff_size(self, patch: Patch) -> CheckDetail:
        """检查 diff 变更行数是否超限。"""
        count = patch.diff_line_count()
        if count <= self.max_patch_lines:
            return CheckDetail(
                name="diff_size_limit",
                passed=True,
                reason=f"变更 {count} 行，≤ 限制 {self.max_patch_lines} 行",
            )
        return CheckDetail(
            name="diff_size_limit",
            passed=False,
            reason=f"变更 {count} 行，超过限制 {self.max_patch_lines} 行",
        )


# ---------------------------------------------------------------------------
# Patch 应用工具
# ---------------------------------------------------------------------------

def _apply_patch(patch: Patch, skill_md: str) -> str | None:
    """尝试应用 patch 到 SKILL.md，返回新内容。

    如果 patch 有 new_content（全文替换模式），直接使用。
    否则尝试基于 unified diff 应用。
    """
    # 全文替换模式
    if patch.new_content:
        return patch.new_content

    # 尝试应用 unified diff
    try:
        return _apply_unified_diff(patch.diff, skill_md)
    except Exception:
        return None


def _apply_unified_diff(diff_text: str, original: str) -> str:
    """简单的 unified diff 应用器。

    仅处理最简单的 @@ ... @@ 块，对于复杂 diff 可能失败。
    """
    import re

    lines = original.splitlines(keepends=True)
    # 确保最后一行有换行
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"

    result = list(lines)

    # 解析 hunks
    hunks = re.findall(
        r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@.*?\n((?:[ +-].*?\n)*)",
        diff_text,
    )

    if not hunks:
        raise ValueError("未找到有效的 diff hunk")

    # 倒序应用 hunks（避免行号偏移）
    offset = 0
    for old_start, old_count, new_start, new_count, body in reversed(hunks):
        old_start = int(old_start) - 1  # 转为 0-indexed
        hunk_lines = body.splitlines(keepends=True)

        # 分离旧行和新行
        old_lines: list[str] = []
        new_lines: list[str] = []
        for hl in hunk_lines:
            if hl.startswith("-"):
                old_lines.append(hl[1:])
            elif hl.startswith("+"):
                new_lines.append(hl[1:])
            elif hl.startswith(" "):
                old_lines.append(hl[1:])
                new_lines.append(hl[1:])

        # 替换
        result[old_start : old_start + len(old_lines)] = new_lines

    return "".join(result)


def _mirror_skill_dir(src: Path, dst: Path) -> None:
    """浅拷贝 skill 目录的非 SKILL.md 文件到临时目录（用于审计）。

    仅拷贝审计需要的文件类型。
    """
    text_exts = {".md", ".py", ".sh", ".json", ".jsonl", ".yaml", ".yml", ".toml", ".txt"}
    try:
        for p in src.rglob("*"):
            if not p.is_file():
                continue
            if p.name == "SKILL.md":
                continue  # 由调用方单独写入
            if p.suffix.lower() not in text_exts:
                continue
            rel = p.relative_to(src)
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(p.read_bytes())
    except OSError:
        pass
