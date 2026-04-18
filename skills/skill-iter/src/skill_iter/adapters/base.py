"""AdapterInterface 抽象基类，内部 adapter 实现不随核心发布。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class AdapterInterface(ABC):
    """可扩展接口，内部 adapter 实现不随核心发布。"""

    def on_init(self, config: dict) -> None:
        """初始化回调。内部可初始化 Bitable token 等。"""

    def on_shutdown(self) -> None:
        """关闭回调。清理资源。"""

    def on_error(self, stage: str, error: Exception) -> None:
        """错误回调。stage 为 audit/evolve/commit 之一。"""

    @abstractmethod
    def on_audit_complete(self, skill_dir: Path, report: dict) -> bool:
        """审计完成回调。返回是否成功。"""

    @abstractmethod
    def on_evolution_proposed(self, skill_dir: Path, patch: dict) -> bool:
        """候选演化生成回调。返回是否成功。"""

    @abstractmethod
    def on_evolution_committed(self, skill_dir: Path, patch: dict) -> bool:
        """演化合入回调。返回是否成功。"""

    @abstractmethod
    def load_trajectories(self, skill_name: str) -> list[Path]:
        """加载轨迹。内部可从 S3/Bitable 拉取。"""
