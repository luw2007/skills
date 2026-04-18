"""补丁生成模块 — LLM 生成 SKILL.md 的 unified diff 补丁。

调用点 2：PatchGenerator，将 SignalExtractor 提取的信号 + 当前 SKILL.md
送入 LLM，输出 unified diff 格式补丁。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from skill_iter.llm import call_llm_text, LLMError
from skill_iter.signal_extractor import Signals


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class Patch:
    """SKILL.md 改进补丁。"""
    diff: str                    # unified diff 格式
    description: str             # 变更说明（1-2 句）
    new_content: str | None      # 全文替换模式时的完整新内容
    base_hash: str               # 基于的 SKILL.md SHA256（用于 commit 时校验一致性）
    signals_summary: dict        # 信号摘要

    def diff_line_count(self) -> int:
        """统计 diff 变更行数（+ 和 - 开头的行）。"""
        count = 0
        for line in self.diff.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                count += 1
            elif line.startswith("-") and not line.startswith("---"):
                count += 1
        return count


# ---------------------------------------------------------------------------
# Prompt 模板
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
你是一个 SKILL.md 编辑专家。根据提供的改进信号，生成对 SKILL.md 的 unified diff 补丁。

要求：
1. 输出格式为标准 unified diff（以 --- a/SKILL.md 和 +++ b/SKILL.md 开头）
2. 仅修改必要部分，保持原有格式和风格一致
3. 不要大面积重写，每次修改控制在 50 行以内
4. 在 diff 之前用一行简短描述变更内容（以 "变更说明:" 开头）
5. 所有文本使用中文"""

_USER_TEMPLATE = """\
## 当前 SKILL.md

```markdown
{skill_md}
```

## 改进信号

### 不变量（不应删除的步骤）
{invariants}

### 修复建议
{fixes}

### 新阶段建议
{new_phases}

请基于以上信号生成 SKILL.md 的 unified diff 补丁。"""

_FULLTEXT_SYSTEM_PROMPT = """\
你是一个 SKILL.md 编辑专家。根据提供的改进信号，输出修改后的完整 SKILL.md 内容。

要求：
1. 仅修改必要部分，保持原有格式和风格一致
2. 不要大面积重写
3. 在输出前用一行简短描述变更内容（以 "变更说明:" 开头），然后空一行，再输出完整 SKILL.md
4. 所有文本使用中文"""


# ---------------------------------------------------------------------------
# 补丁生成器
# ---------------------------------------------------------------------------

class PatchGenerator:
    """LLM 生成 SKILL.md unified diff 补丁。"""

    def __init__(self, model: str, base_url: str | None = None) -> None:
        self.model = model
        self.base_url = base_url

    def generate(self, signals: Signals, skill_md: str) -> Patch:
        """生成 SKILL.md 改进补丁。

        Args:
            signals: 信号提取结果
            skill_md: 当前 SKILL.md 全文

        Returns:
            Patch 对象

        Raises:
            LLMError: LLM 调用失败
        """
        base_hash = hashlib.sha256(skill_md.encode()).hexdigest()

        # 格式化信号
        invariants_text = self._format_invariants(signals)
        fixes_text = self._format_fixes(signals)
        new_phases_text = self._format_new_phases(signals)

        user_prompt = _USER_TEMPLATE.format(
            skill_md=skill_md or "（SKILL.md 为空）",
            invariants=invariants_text,
            fixes=fixes_text,
            new_phases=new_phases_text,
        )

        raw = call_llm_text(
            model=self.model,
            system=_SYSTEM_PROMPT,
            user=user_prompt,
            base_url=self.base_url,
        )

        description, diff = self._parse_response(raw)

        return Patch(
            diff=diff,
            description=description,
            new_content=None,
            base_hash=base_hash,
            signals_summary=signals.to_dict(),
        )

    def generate_fulltext(self, signals: Signals, skill_md: str) -> Patch:
        """降级模式：LLM 输出完整 SKILL.md，用于 diff apply 失败时的 fallback。

        Args:
            signals: 信号提取结果
            skill_md: 当前 SKILL.md 全文

        Returns:
            Patch 对象（new_content 字段有值）
        """
        base_hash = hashlib.sha256(skill_md.encode()).hexdigest()

        invariants_text = self._format_invariants(signals)
        fixes_text = self._format_fixes(signals)
        new_phases_text = self._format_new_phases(signals)

        user_prompt = _USER_TEMPLATE.format(
            skill_md=skill_md or "（SKILL.md 为空）",
            invariants=invariants_text,
            fixes=fixes_text,
            new_phases=new_phases_text,
        )

        raw = call_llm_text(
            model=self.model,
            system=_FULLTEXT_SYSTEM_PROMPT,
            user=user_prompt,
            base_url=self.base_url,
        )

        description, new_content = self._parse_fulltext_response(raw)

        # 生成 diff 用于审查
        import difflib
        diff_lines = difflib.unified_diff(
            skill_md.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile="a/SKILL.md",
            tofile="b/SKILL.md",
        )
        diff = "".join(diff_lines)

        return Patch(
            diff=diff,
            description=description,
            new_content=new_content,
            base_hash=base_hash,
            signals_summary=signals.to_dict(),
        )

    # ------ 内部方法 ------

    @staticmethod
    def _format_invariants(signals: Signals) -> str:
        if not signals.invariants:
            return "（无）"
        return "\n".join(f"- {inv}" for inv in signals.invariants)

    @staticmethod
    def _format_fixes(signals: Signals) -> str:
        if not signals.fixes:
            return "（无）"
        parts: list[str] = []
        for f in signals.fixes:
            parts.append(f"- **{f.target}**: {f.issue} → {f.suggestion}")
        return "\n".join(parts)

    @staticmethod
    def _format_new_phases(signals: Signals) -> str:
        if not signals.new_phases:
            return "（无）"
        parts: list[str] = []
        for p in signals.new_phases:
            parts.append(f"- **{p.name}**: {p.rationale}")
        return "\n".join(parts)

    @staticmethod
    def _parse_response(raw: str) -> tuple[str, str]:
        """解析 LLM 响应，提取描述和 diff。"""
        lines = raw.strip().splitlines()
        description = ""
        diff_start = -1

        for i, line in enumerate(lines):
            if line.startswith("变更说明:") or line.startswith("变更说明："):
                description = line.split(":", 1)[-1].split("：", 1)[-1].strip()
            if line.startswith("---") and i + 1 < len(lines) and lines[i + 1].startswith("+++"):
                diff_start = i
                break

        if diff_start == -1:
            # 尝试找 @@ 标记
            for i, line in enumerate(lines):
                if line.startswith("@@"):
                    diff_start = max(0, i - 2)
                    break

        if diff_start == -1:
            # 无法提取 diff，整个响应作为 diff
            return description or "LLM 生成的补丁", raw.strip()

        diff = "\n".join(lines[diff_start:])
        if not description:
            # 从 diff 之前的内容提取描述
            pre = "\n".join(lines[:diff_start]).strip()
            description = pre[:200] if pre else "LLM 生成的补丁"

        return description, diff

    @staticmethod
    def _parse_fulltext_response(raw: str) -> tuple[str, str]:
        """解析全文替换模式的响应。"""
        lines = raw.strip().splitlines()
        description = ""
        content_start = 0

        for i, line in enumerate(lines):
            if line.startswith("变更说明:") or line.startswith("变更说明："):
                description = line.split(":", 1)[-1].split("：", 1)[-1].strip()
                content_start = i + 1
                # 跳过空行
                while content_start < len(lines) and not lines[content_start].strip():
                    content_start += 1
                break

        content = "\n".join(lines[content_start:])

        # 去除可能的 markdown 代码块包裹
        if content.startswith("```"):
            first_newline = content.index("\n") if "\n" in content else len(content)
            content = content[first_newline + 1:]
        if content.rstrip().endswith("```"):
            content = content.rstrip()[:-3].rstrip()

        return description or "LLM 全文替换", content
