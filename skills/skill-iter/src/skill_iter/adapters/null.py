"""NullAdapter — adapter="none" 时的默认空实现。

所有 hook 均为空操作，不产生任何副作用。
"""
from __future__ import annotations

from pathlib import Path

from skill_iter.adapters.base import AdapterInterface


class NullAdapter(AdapterInterface):
    """空操作 adapter，所有 hook 均直接返回成功。"""

    def on_audit_complete(self, skill_dir: Path, report: dict) -> bool:
        return True

    def on_evolution_proposed(self, skill_dir: Path, patch: dict) -> bool:
        return True

    def on_evolution_committed(self, skill_dir: Path, patch: dict) -> bool:
        return True

    def load_trajectories(self, skill_name: str) -> list[Path]:
        return []
