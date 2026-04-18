"""触发判定模块 — 判断轨迹是否值得启动演化分析。

从 scripts/should_improve.py 迁移并扩展，新增基于轨迹内容的启发式推断。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from skill_iter.trajectory import StructuredTrajectory


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class TriggerResult:
    """触发判定结果。"""
    should: bool
    reason: str


# ---------------------------------------------------------------------------
# 启发式推断用关键词
# ---------------------------------------------------------------------------

_ERROR_KEYWORDS = re.compile(
    r"\b(error|exception|traceback|failed|failure|panic|fatal|crash)\b",
    re.IGNORECASE,
)
_BLOCKING_KEYWORDS = re.compile(
    r"\b(block(?:ed|ing)?|stuck|can'?t proceed|deadlock|timeout|hung)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# 触发判定
# ---------------------------------------------------------------------------

class TriggerJudge:
    """触发判定，决定轨迹是否值得启动演化分析。

    规则优先级（命中第一条即返回）：
    1. category 为 error/blocking → 必须分析
    2. rating <= 2 → 分析
    3. turns > turns_threshold → 成功但低效
    4. 近 N 次平均评分下滑（需要 feedback_history）
    5. 启发式推断（无显式 result 时从内容推断）
    """

    def __init__(self, turns_threshold: int = 20) -> None:
        self.turns_threshold = turns_threshold

    def should_evolve(
        self,
        trajectory: StructuredTrajectory,
        feedback_history: list[dict] | None = None,
    ) -> TriggerResult:
        """判定是否应触发演化。

        Args:
            trajectory: 解析后的轨迹
            feedback_history: 历史反馈记录（来自 feedback-log.json 的 entries），用于趋势分析
        """
        result = trajectory.result
        category = result.category
        rating = result.rating
        turns = result.turns

        # 如果缺少 category/rating，先做启发式推断
        if category is None:
            category = self._infer_category(trajectory)
        if rating is None:
            rating = self._infer_rating(trajectory)

        # 规则 1: 错误或阻塞 → 必须分析
        if category in ("error", "blocking"):
            return TriggerResult(should=True, reason=f"执行类别为 {category}")

        # 规则 2: 评分过低 → 分析
        if rating is not None and rating <= 2:
            return TriggerResult(should=True, reason=f"评分 {rating} <= 2，需分析")

        # 规则 3: 成功但低效（轮数超阈值）
        if turns > self.turns_threshold:
            return TriggerResult(
                should=True,
                reason=f"轮数 {turns} > 阈值 {self.turns_threshold}，成功但低效",
            )

        # 规则 4: 近 5 次平均评分下滑
        if feedback_history:
            trend = self._check_trend(feedback_history, rating)
            if trend is not None:
                return trend

        return TriggerResult(should=False, reason="执行正常，无需演化分析")

    # ------ 启发式推断 ------

    def _infer_category(self, trajectory: StructuredTrajectory) -> str:
        """基于轨迹消息内容推断 category。"""
        all_text = " ".join(m.content for m in trajectory.messages)

        if _BLOCKING_KEYWORDS.search(all_text):
            return "blocking"
        if _ERROR_KEYWORDS.search(all_text):
            return "error"
        return "general"

    @staticmethod
    def _infer_rating(trajectory: StructuredTrajectory) -> int | None:
        """基于轨迹内容启发式推断评分（粗略）。

        无法确定时返回 None，不触发规则 2。
        """
        # 如果轨迹很短（<3 轮），可能是简单任务，不推断
        if len(trajectory.messages) < 3:
            return None
        return None  # 保守策略：不猜测评分，留给人工或 --rating

    @staticmethod
    def _check_trend(
        feedback_history: list[dict],
        current_rating: int | None,
    ) -> TriggerResult | None:
        """检查近 5 次评分趋势。"""
        recent = feedback_history[-5:]
        ratings = [
            e["rating"]
            for e in recent
            if isinstance(e.get("rating"), int)
        ]
        if current_rating is not None:
            ratings.append(current_rating)

        if len(ratings) >= 3:
            avg = sum(ratings) / len(ratings)
            if avg < 3.0:
                return TriggerResult(
                    should=True,
                    reason=f"近 {len(ratings)} 次平均评分 {avg:.1f} < 3.0，呈下滑趋势",
                )
        return None
