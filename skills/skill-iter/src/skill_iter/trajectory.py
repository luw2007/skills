"""轨迹解析器 — 支持格式 A（Markdown）、B（JSON）、C（Claude Code JSONL）自动检测。

从 Agent 会话轨迹文件解析为统一的 StructuredTrajectory 对象。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class Message:
    """单条对话消息。"""
    role: str                                # "user" | "assistant"
    content: str
    tool_calls: list[dict] | None = None     # 可选工具调用记录


@dataclass
class ExecutionResult:
    """执行结果元数据。"""
    rating: int | None = None                # 1-5 评分
    category: str | None = None              # "error" | "blocking" | "general"
    turns: int = 0                           # 对话轮数


@dataclass
class StructuredTrajectory:
    """解析后的统一轨迹对象。"""
    source_path: str                         # 原始文件路径
    format: str                              # "A" | "B" | "C"
    session_id: str | None = None
    skill_name: str | None = None
    messages: list[Message] = field(default_factory=list)
    result: ExecutionResult = field(default_factory=ExecutionResult)
    raw_text: str = ""                       # 原始文本（供截断用）


# ---------------------------------------------------------------------------
# 解析器
# ---------------------------------------------------------------------------

class TrajectoryCollector:
    """轨迹解析器，支持格式 A/B/C 自动检测。"""

    def parse(
        self,
        path: Path,
        *,
        format: str = "auto",
        rating: int | None = None,
    ) -> StructuredTrajectory:
        """解析单个轨迹文件。

        Args:
            path: 轨迹文件路径
            format: "auto" | "A" | "B" | "C"，auto 则自动检测
            rating: 手动提供评分（用于格式 C 无 result 时）

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: 格式检测失败或内容无法解析
        """
        path = Path(path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"轨迹文件不存在: {path}")

        raw = path.read_text(encoding="utf-8")

        if format == "auto":
            detected = self._detect_format(path, raw)
        else:
            detected = format.upper()

        if detected == "C":
            return self._parse_c(path, raw, rating)
        elif detected == "B":
            return self._parse_b(path, raw, rating)
        elif detected == "A":
            return self._parse_a(path, raw, rating)
        else:
            raise ValueError(f"无法识别的轨迹格式: {detected}")

    def parse_dir(
        self,
        dir_path: Path,
        **kwargs,
    ) -> list[StructuredTrajectory]:
        """批量解析目录下所有轨迹文件（.md/.json/.jsonl）。"""
        dir_path = Path(dir_path).resolve()
        if not dir_path.is_dir():
            raise NotADirectoryError(f"目录不存在: {dir_path}")

        results: list[StructuredTrajectory] = []
        for ext in ("*.md", "*.json", "*.jsonl"):
            for f in sorted(dir_path.glob(ext)):
                try:
                    results.append(self.parse(f, **kwargs))
                except (ValueError, json.JSONDecodeError):
                    continue  # 跳过无法解析的文件
        return results

    # ------ 格式检测 ------

    def _detect_format(self, path: Path, raw: str) -> str:
        """自动检测轨迹格式。"""
        suffix = path.suffix.lower()

        # 优先级 1: .jsonl → C
        if suffix == ".jsonl":
            return "C"

        # 优先级 2: .json + 顶层有 session_id → B
        if suffix == ".json":
            try:
                data = json.loads(raw)
                if isinstance(data, dict) and "session_id" in data:
                    return "B"
            except json.JSONDecodeError:
                pass
            # .json 但无 session_id，尝试作为 JSONL 的错误扩展名
            return "B"

        # 优先级 3: .md 且含 ## User / ## Assistant → A
        if suffix == ".md":
            if re.search(r"^##\s+(User|Assistant)", raw, re.MULTILINE):
                return "A"

        raise ValueError(
            f"无法自动检测轨迹格式: {path.name}。"
            "请使用 --format 显式指定（md/json/jsonl）"
        )

    # ------ 格式 A: Markdown ------

    def _parse_a(self, path: Path, raw: str, rating_override: int | None) -> StructuredTrajectory:
        """解析 Markdown 格式轨迹。"""
        messages: list[Message] = []
        result = ExecutionResult()

        # 按 ## 标题分割
        sections = re.split(r"^(##\s+.+)$", raw, flags=re.MULTILINE)

        current_role: str | None = None
        current_content: list[str] = []

        def _flush():
            nonlocal current_role, current_content
            if current_role and current_content:
                text = "\n".join(current_content).strip()
                if current_role in ("user", "assistant"):
                    messages.append(Message(role=current_role, content=text))
                elif current_role == "result":
                    self._parse_result_section(text, result)
            current_content = []

        for section in sections:
            header_match = re.match(r"^##\s+(.+)$", section.strip())
            if header_match:
                _flush()
                title = header_match.group(1).strip().lower()
                if "user" in title:
                    current_role = "user"
                elif "assistant" in title:
                    current_role = "assistant"
                elif "result" in title or "execution" in title:
                    current_role = "result"
                else:
                    current_role = None
            else:
                if current_role:
                    current_content.append(section)

        _flush()

        # 补充 result
        if not result.turns:
            result.turns = sum(1 for m in messages if m.role == "user")
        if rating_override is not None:
            result.rating = rating_override

        return StructuredTrajectory(
            source_path=str(path),
            format="A",
            messages=messages,
            result=result,
            raw_text=raw,
        )

    @staticmethod
    def _parse_result_section(text: str, result: ExecutionResult) -> None:
        """从 Execution Result 文本中提取 rating/category/turns。"""
        for line in text.splitlines():
            line = line.strip()
            m = re.match(r"rating\s*:\s*(\d+)", line, re.IGNORECASE)
            if m:
                result.rating = int(m.group(1))
            m = re.match(r"category\s*:\s*(\w+)", line, re.IGNORECASE)
            if m:
                result.category = m.group(1)
            m = re.match(r"turns\s*:\s*(\d+)", line, re.IGNORECASE)
            if m:
                result.turns = int(m.group(1))

    # ------ 格式 B: JSON ------

    def _parse_b(self, path: Path, raw: str, rating_override: int | None) -> StructuredTrajectory:
        """解析 JSON 格式轨迹。"""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON 解析失败: {path.name}: {e}") from e

        if not isinstance(data, dict):
            raise ValueError(f"JSON 顶层必须是对象: {path.name}")

        messages: list[Message] = []
        for msg in data.get("messages", []):
            if not isinstance(msg, dict):
                continue
            messages.append(Message(
                role=msg.get("role", "user"),
                content=self._extract_content(msg.get("content", "")),
                tool_calls=msg.get("tool_calls"),
            ))

        res_data = data.get("result", {}) or {}
        result = ExecutionResult(
            rating=rating_override if rating_override is not None else res_data.get("rating"),
            category=res_data.get("category"),
            turns=res_data.get("turns", len([m for m in messages if m.role == "user"])),
        )

        return StructuredTrajectory(
            source_path=str(path),
            format="B",
            session_id=data.get("session_id"),
            skill_name=data.get("skill_name"),
            messages=messages,
            result=result,
            raw_text=raw,
        )

    # ------ 格式 C: Claude Code JSONL ------

    def _parse_c(self, path: Path, raw: str, rating_override: int | None) -> StructuredTrajectory:
        """解析 Claude Code JSONL 格式轨迹。"""
        messages: list[Message] = []
        has_error = False

        for i, line in enumerate(raw.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue  # 跳过格式错误的行

            if not isinstance(entry, dict):
                continue

            msg_data = entry.get("message", entry)
            if not isinstance(msg_data, dict):
                continue

            role = msg_data.get("role", entry.get("type", ""))
            # Claude Code 使用 type: "human"/"assistant"
            if role == "human" or entry.get("type") == "human":
                role = "user"
            elif role not in ("user", "assistant"):
                if entry.get("type") == "assistant":
                    role = "assistant"
                else:
                    continue

            content = self._extract_content(msg_data.get("content", ""))
            tool_calls = msg_data.get("tool_calls")

            # 检测错误关键词
            if any(kw in content.lower() for kw in ("error", "exception", "traceback", "failed")):
                has_error = True

            messages.append(Message(role=role, content=content, tool_calls=tool_calls))

        if not messages:
            raise ValueError(f"JSONL 文件中未找到有效消息: {path.name}")

        user_turns = sum(1 for m in messages if m.role == "user")
        category = "error" if has_error else "general"

        result = ExecutionResult(
            rating=rating_override,
            category=category,
            turns=user_turns,
        )

        return StructuredTrajectory(
            source_path=str(path),
            format="C",
            messages=messages,
            result=result,
            raw_text=raw,
        )

    # ------ 工具方法 ------

    @staticmethod
    def _extract_content(content) -> str:
        """提取消息内容，兼容 str 和 list（Claude API 格式）。"""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    parts.append(item.get("text", ""))
            return "\n".join(parts)
        return str(content)
