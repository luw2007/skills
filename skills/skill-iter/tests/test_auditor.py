"""Auditor D1-D7 审计引擎单元测试。"""
from __future__ import annotations

import json
import pytest
from pathlib import Path

from skill_iter.auditor import Auditor, AuditReport, Grade, DimensionResult, _audit_cache


@pytest.fixture(autouse=True)
def clear_cache():
    _audit_cache.clear()
    yield
    _audit_cache.clear()


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

FULL_SKILL_MD = """\
---
name: test-skill
description: 测试用 skill
---

# Test Skill

## Phase 1: 执行

正常执行步骤。

## Phase 2: 自检回顾 (retrospective)

执行反馈采集，记录 rating/turns/category。
轨迹摘要与工具调用统计。

触发判定(should_improve)：失败、阻塞、成功但低效（turns > threshold）均触发。
自定义触发规则可通过配置调整。

分析能力：三分法 codify / lesson / ignore。
LLM 分析轨迹提取信号 (llm_extract)。

闭环路径：Agent 读取 SKILL.md → 执行 → 写入 Lessons Learned → 下次读取自动包含。
动态筛选注入最相关经验。

安全：.pending_evolution 目录 + 人工确认 + threat_scan 注入检测。

可观测性：improvement-log.json 记录 session_id / timestamp / reason。
versions.json 支持回滚。

## Lessons Learned

- 经验条目 1
- 经验条目 2

## 配置

max_entries = 10，FIFO 淘汰，去重 dedup。
语义去重 semantic_dedup，LRU 策略。
"""


def _create_full_skill(tmp_path: Path) -> Path:
    """创建一个完整的 skill 目录。"""
    skill_dir = tmp_path / "full-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(FULL_SKILL_MD, encoding="utf-8")

    # scripts 目录
    scripts = skill_dir / "scripts"
    scripts.mkdir()
    for name in [
        "collect_feedback.py",
        "should_improve.py",
        "analyze_trajectory.py",
        "merge_lessons.py",
        "run_retrospective.py",
        "threat_scan.py",
    ]:
        (scripts / name).write_text(f"# {name}\n", encoding="utf-8")

    # reports 目录
    reports = skill_dir / "reports"
    reports.mkdir()
    (reports / "improvement-log.json").write_text(
        json.dumps({"entries": [{"session_id": "s1", "timestamp": "2026-01-01", "reason": "test"}]}),
        encoding="utf-8",
    )

    # .pending_evolution 目录
    pending = skill_dir / ".pending_evolution"
    pending.mkdir()

    return skill_dir


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------

class TestAuditEmptyDir:
    def test_all_missing(self, tmp_path: Path) -> None:
        """空目录（无 SKILL.md），所有维度应为 MISSING。"""
        skill_dir = tmp_path / "empty-skill"
        skill_dir.mkdir()
        report = Auditor(skill_dir).audit()
        assert len(report.dimensions) == 7
        for dim in report.dimensions:
            assert dim.grade == Grade.MISSING, f"{dim.dimension} should be MISSING, got {dim.grade}"
        assert report.total_missing == 7
        assert report.total_good == 0


class TestAuditMinimalSkill:
    def test_d4_at_least_basic(self, tmp_path: Path) -> None:
        """仅有 SKILL.md 含 Lessons Learned，D4 至少 BASIC。"""
        skill_dir = tmp_path / "minimal"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "# My Skill\n\n## Lessons Learned\n\n- 经验 1\n",
            encoding="utf-8",
        )
        report = Auditor(skill_dir).audit()
        d4 = next(d for d in report.dimensions if d.dimension == "D4")
        assert d4.grade in (Grade.BASIC, Grade.GOOD, Grade.EXCELLENT)


class TestAuditFullSkill:
    def test_multiple_good_or_better(self, tmp_path: Path) -> None:
        """完整 skill 目录，多个维度应 GOOD+。"""
        skill_dir = _create_full_skill(tmp_path)
        report = Auditor(skill_dir).audit()
        good_or_better = [
            d for d in report.dimensions
            if d.grade in (Grade.GOOD, Grade.EXCELLENT)
        ]
        # 至少 5 个维度达标
        assert len(good_or_better) >= 5, (
            f"Expected >= 5 GOOD+, got {len(good_or_better)}: "
            + ", ".join(f"{d.dimension}={d.grade.value}" for d in report.dimensions)
        )


class TestToDict:
    def test_keys(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "dict-test"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Test\n", encoding="utf-8")
        report = Auditor(skill_dir).audit()
        d = report.to_dict()
        assert "skill_name" in d
        assert "dimensions" in d
        assert "total_good" in d
        assert "total_basic" in d
        assert "total_missing" in d
        assert "skill_dir" in d
        assert len(d["dimensions"]) == 7


class TestToTable:
    def test_contains_headers(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "table-test"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Test\n", encoding="utf-8")
        report = Auditor(skill_dir).audit()
        table = report.to_table()
        assert "维度" in table
        assert "等级" in table
        assert "说明" in table
        assert "D1" in table
        assert "总评" in table


class TestCiExitCode:
    def test_pass(self) -> None:
        """全部 GOOD 时 exit code = 0。"""
        dims = [
            DimensionResult(f"D{i}", f"dim{i}", Grade.GOOD, "ok")
            for i in range(1, 8)
        ]
        report = AuditReport(skill_dir="/tmp/x", skill_name="x", dimensions=dims)
        assert report.ci_exit_code() == 0

    def test_fail(self) -> None:
        """有 MISSING 时 exit code = 1。"""
        dims = [
            DimensionResult(f"D{i}", f"dim{i}", Grade.GOOD, "ok")
            for i in range(1, 7)
        ]
        dims.append(DimensionResult("D7", "dim7", Grade.MISSING, "no"))
        report = AuditReport(skill_dir="/tmp/x", skill_name="x", dimensions=dims)
        assert report.ci_exit_code() == 1


class TestCache:
    def test_same_object(self, tmp_path: Path) -> None:
        """连续两次 audit 同一目录应命中缓存（返回同一对象）。"""
        skill_dir = tmp_path / "cache-test"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Cache Test\n", encoding="utf-8")
        auditor = Auditor(skill_dir)
        r1 = auditor.audit()
        r2 = auditor.audit()
        assert r1 is r2
