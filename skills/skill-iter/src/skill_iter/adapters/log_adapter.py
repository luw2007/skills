"""LogAdapter — 日志记录 adapter，用于开发调试和作为内部 adapter 开发参考。

所有 hook 通过 logging 输出事件信息，不执行任何外部操作。
配置示例（pyproject.toml）：
    [tool.skill-iter]
    adapter = "log"
"""
from __future__ import annotations

import logging
from pathlib import Path

from skill_iter.adapters.base import AdapterInterface

logger = logging.getLogger("skill-iter.adapter.log")


class LogAdapter(AdapterInterface):
    """日志 adapter — 记录所有 hook 调用，方便调试。"""

    def on_init(self, config: dict) -> None:
        logger.info("LogAdapter 初始化, config keys: %s", list(config.keys()))

    def on_shutdown(self) -> None:
        logger.info("LogAdapter 关闭")

    def on_error(self, stage: str, error: Exception) -> None:
        logger.error("LogAdapter 错误 [%s]: %s", stage, error)

    def on_audit_complete(self, skill_dir: Path, report: dict) -> bool:
        score = report.get("total_score", "?")
        dims = len(report.get("dimensions", []))
        logger.info("审计完成: skill_dir=%s, 总分=%s, 维度数=%d", skill_dir, score, dims)
        return True

    def on_evolution_proposed(self, skill_dir: Path, patch: dict) -> bool:
        patch_id = patch.get("patch_id", "?")
        desc = patch.get("description", "")[:80]
        logger.info("候选演化生成: skill_dir=%s, patch_id=%s, desc=%s", skill_dir, patch_id, desc)
        return True

    def on_evolution_committed(self, skill_dir: Path, patch: dict) -> bool:
        patch_id = patch.get("patch_id", "?")
        logger.info("演化已合入: skill_dir=%s, patch_id=%s", skill_dir, patch_id)
        return True

    def load_trajectories(self, skill_name: str) -> list[Path]:
        logger.info("加载轨迹请求: skill_name=%s (LogAdapter 不提供轨迹)", skill_name)
        return []
