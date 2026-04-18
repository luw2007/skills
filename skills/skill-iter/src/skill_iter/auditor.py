"""D1-D7 纯规则审计引擎，不依赖 LLM，通过正则/文件扫描检测 Skill 自迭代能力。"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

class Grade(str, Enum):
    MISSING = "missing"      # ❌
    BASIC = "basic"          # ⚠️
    GOOD = "good"            # ✅
    EXCELLENT = "excellent"  # 🌟

_GRADE_ICON = {
    Grade.MISSING: "❌",
    Grade.BASIC: "⚠️",
    Grade.GOOD: "✅",
    Grade.EXCELLENT: "🌟",
}


@dataclass
class DimensionResult:
    dimension: str          # "D1" ~ "D7"
    name: str               # "反馈采集" 等
    grade: Grade
    reason: str             # 判定理由
    suggestions: list[str] = field(default_factory=list)  # 仅非 good/excellent 时


@dataclass
class AuditReport:
    skill_dir: str
    skill_name: str
    dimensions: list[DimensionResult]
    total_good: int = 0      # ✅ + 🌟
    total_basic: int = 0
    total_missing: int = 0

    def __post_init__(self) -> None:
        self.total_good = sum(
            1 for d in self.dimensions if d.grade in (Grade.GOOD, Grade.EXCELLENT)
        )
        self.total_basic = sum(
            1 for d in self.dimensions if d.grade == Grade.BASIC
        )
        self.total_missing = sum(
            1 for d in self.dimensions if d.grade == Grade.MISSING
        )

    def to_dict(self) -> dict:
        return {
            "skill_dir": self.skill_dir,
            "skill_name": self.skill_name,
            "dimensions": [
                {
                    "dimension": d.dimension,
                    "name": d.name,
                    "grade": d.grade.value,
                    "reason": d.reason,
                    "suggestions": d.suggestions,
                }
                for d in self.dimensions
            ],
            "total_good": self.total_good,
            "total_basic": self.total_basic,
            "total_missing": self.total_missing,
        }

    def to_table(self) -> str:
        lines: list[str] = [
            f"📊 自迭代能力评审报告 — {self.skill_name}",
            "",
            "| 维度 | 等级 | 说明 |",
            "|------|------|------|",
        ]
        for d in self.dimensions:
            icon = _GRADE_ICON[d.grade]
            lines.append(f"| {d.dimension} {d.name} | {icon} | {d.reason} |")
        lines.append("")
        lines.append(
            f"总评：✅ 达标 {self.total_good}/7 | "
            f"⚠️ 基础 {self.total_basic}/7 | "
            f"❌ 缺失 {self.total_missing}/7"
        )
        return "\n".join(lines)

    def ci_exit_code(self) -> int:
        """0=全部达标（无 missing），1=有缺失。"""
        return 0 if self.total_missing == 0 else 1


# ---------------------------------------------------------------------------
# 审计缓存：同一 SKILL.md hash 复用
# ---------------------------------------------------------------------------
_audit_cache: dict[str, AuditReport] = {}


# ---------------------------------------------------------------------------
# 审计引擎
# ---------------------------------------------------------------------------

class Auditor:
    def __init__(self, skill_dir: Path) -> None:
        self.skill_dir = skill_dir.resolve()
        self._skill_md_text: str | None = None
        self._all_text_cache: str | None = None

    # ------ 公开 API ------

    def audit(self) -> AuditReport:
        """执行完整 D1-D7 审计，支持基于 SKILL.md 内容 hash 的缓存。"""
        md_text = self._load_skill_md()
        cache_key = hashlib.sha256(md_text.encode()).hexdigest()
        if cache_key in _audit_cache:
            return _audit_cache[cache_key]

        skill_name = self.skill_dir.name
        dims = [
            self._audit_d1(),
            self._audit_d2(),
            self._audit_d3(),
            self._audit_d4(),
            self._audit_d5(),
            self._audit_d6(),
            self._audit_d7(),
        ]
        report = AuditReport(
            skill_dir=str(self.skill_dir),
            skill_name=skill_name,
            dimensions=dims,
        )
        _audit_cache[cache_key] = report
        return report

    # ------ D1: 反馈采集 ------

    def _audit_d1(self) -> DimensionResult:
        dim, name = "D1", "反馈采集"

        has_phase = self._skill_md_contains(
            r"(?i)(自检|retrospective|迭代|review|回顾).*phase"
        ) or self._skill_md_contains(
            r"(?i)phase.*?(自检|retrospective|迭代|review|回顾)"
        ) or self._skill_md_contains(
            r"(?i)##.*?(自检|retrospective|迭代|review|回顾)"
        )
        has_feedback_file = self._has_file_matching(
            "collect_feedback", "feedback-log", "collect_feedback*", "feedback*"
        )
        has_rating_fields = self._all_text_contains(
            r"(?i)(rating|turns|category)"
        )
        has_advanced = self._all_text_contains(
            r"(?i)(轨迹摘要|trajectory.?summary|耗时分布|duration.?distribut|工具调用统计|tool.?call.?stat)"
        )

        # 🌟 优秀
        if has_phase and has_feedback_file and has_rating_fields and has_advanced:
            return DimensionResult(dim, name, Grade.EXCELLENT,
                                   "有自检阶段 + 反馈采集脚本 + 多维字段 + 高级统计")
        # ✅ 达标
        if has_phase and has_feedback_file and has_rating_fields:
            return DimensionResult(dim, name, Grade.GOOD,
                                   "有自检阶段 + 反馈采集脚本 + 采集 rating/turns/category")
        # ⚠️ 基础
        if has_feedback_file or self._skill_md_contains(r"(?i)(feedback|反馈|成功|失败)"):
            return DimensionResult(dim, name, Grade.BASIC,
                                   "仅记录成功/失败，缺少结构化采集",
                                   ["添加自检阶段到 SKILL.md Phase 定义",
                                    "创建 collect_feedback 脚本，采集 rating/turns/category"])
        # ❌ 缺失
        return DimensionResult(dim, name, Grade.MISSING,
                               "无反馈采集相关代码或自检阶段",
                               ["在 SKILL.md 中增加自检/回顾 Phase",
                                "创建 collect_feedback 脚本",
                                "采集 rating、turns、category 字段"])

    # ------ D2: 触发判定 ------

    def _audit_d2(self) -> DimensionResult:
        dim, name = "D2", "触发判定"

        has_trigger_file = self._has_file_matching(
            "should_improve", "trigger", "should_trigger*", "trigger*"
        )
        has_trigger_desc = self._skill_md_contains(
            r"(?i)(触发|trigger|should.?improve)"
        )
        covers_error = self._all_text_contains(r"(?i)(error|失败|fail)")
        covers_blocking = self._all_text_contains(r"(?i)(block|阻塞|stuck|卡住)")
        covers_inefficient = self._all_text_contains(
            r"(?i)(低效|inefficien|成功但|too.?many.?turns|高轮次)"
        )
        has_custom = self._all_text_contains(
            r"(?i)(custom.?trigger|自定义触发|trigger.?rule|触发规则配置)"
        )

        all_three = covers_error and covers_blocking and covers_inefficient

        if (has_trigger_file or has_trigger_desc) and all_three and has_custom:
            return DimensionResult(dim, name, Grade.EXCELLENT,
                                   "覆盖 error/blocking/低效 + 支持自定义触发规则")
        if (has_trigger_file or has_trigger_desc) and all_three:
            return DimensionResult(dim, name, Grade.GOOD,
                                   "失败 + 阻塞 + 低效均触发")
        if has_trigger_file or has_trigger_desc:
            return DimensionResult(dim, name, Grade.BASIC,
                                   "有触发逻辑但未覆盖全部场景",
                                   ["补充阻塞/低效场景的触发判定",
                                    "在 should_improve 中同时检测 error/blocking/低效"])
        return DimensionResult(dim, name, Grade.MISSING,
                               "无触发判定逻辑",
                               ["创建 should_improve 触发判定模块",
                                "覆盖 error、blocking、低效三类场景"])

    # ------ D3: 分析能力 ------

    def _audit_d3(self) -> DimensionResult:
        dim, name = "D3", "分析能力"

        has_analyzer_file = self._has_file_matching(
            "analyze_trajectory", "signal_extractor", "analyzer*", "signal*"
        )
        has_triage = self._skill_md_contains(
            r"(?i)(三分法|codify|lesson|ignore|triage)"
        ) or self._all_text_contains(
            r"(?i)(codify|lesson|ignore)"
        )
        has_llm_analysis = self._all_text_contains(
            r"(?i)(llm.?分析|轨迹分析|trajectory.?analy|llm.?extract)"
        )

        if has_analyzer_file and has_triage and has_llm_analysis:
            return DimensionResult(dim, name, Grade.EXCELLENT,
                                   "结构化分析 + 三分法 + LLM 轨迹分析")
        if has_analyzer_file and has_triage:
            return DimensionResult(dim, name, Grade.GOOD,
                                   "结构化分析 + 三分法（codify/lesson/ignore）")
        if has_analyzer_file or self._skill_md_contains(r"(?i)(分析|review|analy)"):
            return DimensionResult(dim, name, Grade.BASIC,
                                   "仅人工回顾或基础分析",
                                   ["实现结构化分析模块",
                                    "引入三分法：codify / lesson / ignore"])
        return DimensionResult(dim, name, Grade.MISSING,
                               "无分析能力",
                               ["创建 analyze_trajectory 或 signal_extractor 模块",
                                "在 SKILL.md 中描述三分法分类"])

    # ------ D4: 经验持久化 ------

    def _audit_d4(self) -> DimensionResult:
        dim, name = "D4", "经验持久化"

        has_lessons_section = self._skill_md_contains(
            r"(?i)##\s*Lessons?\s+Learned"
        )
        has_merge_file = self._has_file_matching(
            "merge_lessons", "pending", "merge*", "lesson*"
        )
        has_eviction = self._all_text_contains(
            r"(?i)(max.?entries|FIFO|淘汰|evict|去重|dedup)"
        )
        has_semantic_dedup = self._all_text_contains(
            r"(?i)(语义去重|semantic.?dedup|LRU|embedding.?dedup)"
        )

        if has_lessons_section and has_merge_file and has_eviction and has_semantic_dedup:
            return DimensionResult(dim, name, Grade.EXCELLENT,
                                   "Lessons Learned + 去重 + 语义去重/LRU")
        if has_lessons_section and (has_merge_file or has_eviction):
            return DimensionResult(dim, name, Grade.GOOD,
                                   "有 Lessons Learned 章节 + 去重/FIFO 淘汰")
        if has_lessons_section or has_merge_file:
            return DimensionResult(dim, name, Grade.BASIC,
                                   "手动维护经验，缺少自动化",
                                   ["在 SKILL.md 中添加 ## Lessons Learned 章节",
                                    "实现 merge_lessons 自动合入 + FIFO 淘汰"])
        return DimensionResult(dim, name, Grade.MISSING,
                               "无经验持久化",
                               ["在 SKILL.md 中添加 ## Lessons Learned 章节",
                                "创建 merge_lessons 脚本 + .pending 流程",
                                "设置 max_entries + FIFO 淘汰策略"])

    # ------ D5: 注入闭环 ------

    def _audit_d5(self) -> DimensionResult:
        dim, name = "D5", "注入闭环"

        has_loop_desc = self._skill_md_contains(
            r"(?i)(闭环|closed.?loop|读取.*执行.*写入|read.*execute.*write)"
        )
        has_retro_file = self._has_file_matching(
            "run_retrospective", "retrospective*", "orchestrat*", "编排*"
        )
        has_auto_include = self._skill_md_contains(
            r"(?i)(自动包含|auto.?include|自动注入|auto.?inject|Lessons.?Learned.*执行|执行.*Lessons.?Learned)"
        )
        has_dynamic_filter = self._all_text_contains(
            r"(?i)(动态筛选|dynamic.?filter|relevance.?filter|相关性筛选)"
        )

        if (has_loop_desc or has_retro_file) and has_auto_include and has_dynamic_filter:
            return DimensionResult(dim, name, Grade.EXCELLENT,
                                   "闭环路径完整 + 自动包含 + 动态筛选注入")
        if (has_loop_desc or has_retro_file) and has_auto_include:
            return DimensionResult(dim, name, Grade.GOOD,
                                   "执行时自动包含 Lessons Learned")
        if has_loop_desc or has_retro_file:
            return DimensionResult(dim, name, Grade.BASIC,
                                   "有编排脚本但需人工提醒注入",
                                   ["在执行阶段自动读取 Lessons Learned",
                                    "实现「读取 → 执行 → 写入 → 下次读取」闭环"])
        return DimensionResult(dim, name, Grade.MISSING,
                               "写了但不读，无注入闭环",
                               ["在 SKILL.md 中描述闭环路径",
                                "创建 run_retrospective 编排脚本",
                                "确保执行时自动包含 Lessons Learned"])

    # ------ D6: 安全门禁 ------

    def _audit_d6(self) -> DimensionResult:
        dim, name = "D6", "安全门禁"

        has_pending = self._has_file_matching(
            ".pending", "pending*", "*.pending"
        ) or self._all_text_contains(r"(?i)(\.pending|pending.?evolution)")
        has_human_confirm = self._all_text_contains(
            r"(?i)(人工确认|human.?confirm|human.?review|approve|审批)"
        )
        has_threat_scan = self._has_file_matching(
            "threat_scan", "injection*", "security*"
        ) or self._all_text_contains(
            r"(?i)(threat.?scan|injection.?detect|prompt.?inject|安全扫描|注入检测)"
        )
        has_git_only = self._all_text_contains(
            r"(?i)(git\s+diff|git\s+commit|version.?control)"
        ) and not has_pending

        if has_pending and has_human_confirm and has_threat_scan:
            return DimensionResult(dim, name, Grade.EXCELLENT,
                                   ".pending 机制 + 人工确认 + prompt 注入检测")
        if has_pending and has_human_confirm:
            return DimensionResult(dim, name, Grade.GOOD,
                                   ".pending 机制 + 人工确认")
        if has_git_only or has_pending or has_human_confirm:
            return DimensionResult(dim, name, Grade.BASIC,
                                   "仅依赖 git 或部分审核",
                                   ["实现 .pending 机制，补丁先落盘待确认",
                                    "添加人工确认步骤"])
        return DimensionResult(dim, name, Grade.MISSING,
                               "无安全审核机制",
                               ["创建 .pending_evolution 目录机制",
                                "补丁写入 .pending 后须人工确认",
                                "考虑添加 prompt 注入检测"])

    # ------ D7: 可观测性 ------

    def _audit_d7(self) -> DimensionResult:
        dim, name = "D7", "可观测性"

        has_log_file = self._has_file_matching(
            "improvement-log", "evolve-log", "improvement_log*", "evolve_log*"
        )
        has_log_desc = self._skill_md_contains(
            r"(?i)(improvement.?log|evolve.?log|可观测|observab|审计日志|audit.?log)"
        )
        has_structured = self._all_text_contains(
            r"(?i)(session.?id|时间戳|timestamp|原因|reason)"
        )
        has_versions = self._has_file_matching(
            "versions.json", "versions*"
        ) or self._all_text_contains(
            r"(?i)(versions\.json|回滚|rollback)"
        )

        if (has_log_file or has_log_desc) and has_structured and has_versions:
            return DimensionResult(dim, name, Grade.EXCELLENT,
                                   "improvement-log + 结构化字段 + versions.json 回滚支持")
        if (has_log_file or has_log_desc) and has_structured:
            return DimensionResult(dim, name, Grade.GOOD,
                                   "improvement-log 有 session_id + 时间戳 + 原因")
        if has_log_file or has_log_desc:
            return DimensionResult(dim, name, Grade.BASIC,
                                   "仅 git log 或基础日志",
                                   ["improvement-log.json 中记录 session_id、时间戳、原因",
                                    "考虑添加 versions.json 支持回滚"])
        return DimensionResult(dim, name, Grade.MISSING,
                               "无追溯能力",
                               ["创建 improvement-log.json 结构化日志",
                                "记录 session_id、timestamp、reason",
                                "添加 versions.json + 回滚支持"])

    # ------ 内部工具方法 ------

    def _load_skill_md(self) -> str:
        """加载 SKILL.md 文本，缓存到实例。"""
        if self._skill_md_text is not None:
            return self._skill_md_text
        skill_md = self.skill_dir / "SKILL.md"
        if skill_md.exists():
            self._skill_md_text = skill_md.read_text(encoding="utf-8")
        else:
            self._skill_md_text = ""
        return self._skill_md_text

    def _has_file_matching(self, *patterns: str) -> bool:
        """检查 skill_dir 下是否有文件名包含任一 pattern（大小写不敏感）。"""
        try:
            all_files = [
                p.name.lower()
                for p in self.skill_dir.rglob("*")
                if p.is_file()
            ]
        except OSError:
            return False
        for pat in patterns:
            pat_lower = pat.lower()
            for fname in all_files:
                if pat_lower in fname:
                    return True
        return False

    def _skill_md_contains(self, pattern: str) -> bool:
        """正则匹配 SKILL.md 内容。"""
        text = self._load_skill_md()
        if not text:
            return False
        return bool(re.search(pattern, text))

    def _load_all_text(self) -> str:
        """拼接 skill_dir 下所有文本文件内容（用于全局关键词搜索），缓存到实例。"""
        if self._all_text_cache is not None:
            return self._all_text_cache
        text_exts = {".md", ".py", ".sh", ".json", ".jsonl", ".yaml", ".yml", ".toml", ".txt", ".cfg"}
        parts: list[str] = []
        try:
            for p in sorted(self.skill_dir.rglob("*")):
                if p.is_file() and p.suffix.lower() in text_exts:
                    try:
                        parts.append(p.read_text(encoding="utf-8", errors="ignore"))
                    except OSError:
                        continue
        except OSError:
            pass
        self._all_text_cache = "\n".join(parts)
        return self._all_text_cache

    def _all_text_contains(self, pattern: str) -> bool:
        """正则匹配 skill_dir 下所有文本文件的拼接内容。"""
        text = self._load_all_text()
        if not text:
            return False
        return bool(re.search(pattern, text))
