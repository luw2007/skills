"""信号提取模块 — LLM 分析轨迹，提取不变量、修复建议和新阶段信号。

调用点 1：SignalExtractor，将轨迹 + 当前 SKILL.md 送入 LLM，
输出结构化 JSON {invariants, fixes, new_phases}。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from skill_iter.llm import call_llm_json, LLMError, LLMParseError
from skill_iter.trajectory import StructuredTrajectory


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class Fix:
    """单条修复建议。"""
    target: str       # 修复目标位置（如 "Phase 2 Step 3"）
    issue: str        # 问题描述
    suggestion: str   # 修复建议


@dataclass
class NewPhase:
    """新阶段建议。"""
    name: str         # 阶段名称
    rationale: str    # 添加理由


@dataclass
class Signals:
    """从轨迹中提取的信号集合。"""
    invariants: list[str] = field(default_factory=list)   # 不可删除的稳定步骤
    fixes: list[Fix] = field(default_factory=list)         # 修复建议
    new_phases: list[NewPhase] = field(default_factory=list)  # 新阶段建议
    raw_response: dict = field(default_factory=dict)       # LLM 原始响应（用于门禁扫描）

    def to_dict(self) -> dict:
        return {
            "invariants": self.invariants,
            "fixes": [
                {"target": f.target, "issue": f.issue, "suggestion": f.suggestion}
                for f in self.fixes
            ],
            "new_phases": [
                {"name": p.name, "rationale": p.rationale}
                for p in self.new_phases
            ],
        }


# ---------------------------------------------------------------------------
# Prompt 模板
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
你是一个 Skill 演化分析专家。你的任务是分析 Agent 会话轨迹，提取可用于改进 SKILL.md 的信号。

输出格式为严格 JSON（不要包含 markdown 代码块标记）：
{
  "invariants": ["步骤 X 在所有成功 case 中都被执行，不可删除"],
  "fixes": [{"target": "Phase 2 Step 3", "issue": "缺少错误处理", "suggestion": "添加 fallback"}],
  "new_phases": [{"name": "参数校验", "rationale": "3 次失败均因输入格式错误"}]
}

规则：
- invariants: 在轨迹中表现为稳定有效的步骤，不应被删除
- fixes: 轨迹中暴露的问题，需要修改 SKILL.md 对应位置
- new_phases: 轨迹中频繁出现但 SKILL.md 未覆盖的新阶段
- 每类信号 0-5 条，精准而非冗余
- 所有文本使用中文"""

_USER_TEMPLATE = """\
## 当前 SKILL.md

{skill_md}

## 会话轨迹

{trajectory}

## 执行结果

- 评分: {rating}
- 类别: {category}
- 轮数: {turns}

请分析以上轨迹，提取改进信号。"""


# ---------------------------------------------------------------------------
# 轨迹截断
# ---------------------------------------------------------------------------

def _truncate_trajectory(trajectory: StructuredTrajectory, max_tokens: int) -> str:
    """截断轨迹文本，采用头尾保留、中间截断策略。

    粗略按字符估算 token（中文约 1.5 字符/token，英文约 4 字符/token，取 2.5 均值）。
    """
    raw = trajectory.raw_text
    max_chars = int(max_tokens * 2.5)

    if len(raw) <= max_chars:
        return raw

    # 头尾各保留 40%，中间截断
    head_size = int(max_chars * 0.4)
    tail_size = int(max_chars * 0.4)
    return (
        raw[:head_size]
        + f"\n\n... [截断 {len(raw) - head_size - tail_size} 字符] ...\n\n"
        + raw[-tail_size:]
    )


# ---------------------------------------------------------------------------
# 信号提取器
# ---------------------------------------------------------------------------

class SignalExtractor:
    """从轨迹中提取演化信号（调用 LLM）。"""

    def __init__(self, model: str, base_url: str | None = None, max_trajectory_tokens: int = 16000) -> None:
        self.model = model
        self.base_url = base_url
        self.max_trajectory_tokens = max_trajectory_tokens

    def extract(self, trajectory: StructuredTrajectory, skill_md: str) -> Signals:
        """分析轨迹，提取信号。

        Args:
            trajectory: 解析后的轨迹
            skill_md: 当前 SKILL.md 全文

        Returns:
            Signals 对象

        Raises:
            LLMError: LLM 调用失败
            LLMParseError: JSON 解析失败（重试后仍失败）
        """
        truncated = _truncate_trajectory(trajectory, self.max_trajectory_tokens)

        result = trajectory.result
        user_prompt = _USER_TEMPLATE.format(
            skill_md=skill_md or "（SKILL.md 为空）",
            trajectory=truncated,
            rating=result.rating if result.rating is not None else "未知",
            category=result.category or "未知",
            turns=result.turns,
        )

        data = call_llm_json(
            model=self.model,
            system=_SYSTEM_PROMPT,
            user=user_prompt,
            base_url=self.base_url,
        )

        return self._parse_signals(data)

    @staticmethod
    def _parse_signals(data: dict) -> Signals:
        """将 LLM 输出的 dict 解析为 Signals 对象。"""
        invariants = data.get("invariants", [])
        if not isinstance(invariants, list):
            invariants = []

        fixes: list[Fix] = []
        for item in data.get("fixes", []):
            if isinstance(item, dict):
                fixes.append(Fix(
                    target=item.get("target", ""),
                    issue=item.get("issue", ""),
                    suggestion=item.get("suggestion", ""),
                ))

        new_phases: list[NewPhase] = []
        for item in data.get("new_phases", []):
            if isinstance(item, dict):
                new_phases.append(NewPhase(
                    name=item.get("name", ""),
                    rationale=item.get("rationale", ""),
                ))

        return Signals(
            invariants=[str(i) for i in invariants],
            fixes=fixes,
            new_phases=new_phases,
            raw_response=data,
        )
