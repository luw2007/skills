"""Watcher 守护进程 — 监听轨迹目录，自动触发演化管线。

设计要点（spec §10）：
- 执行模型：串行队列（FIFO），避免并发 patch 冲突
- 状态持久化：.watch_state.json 记录已处理轨迹的 path + mtime，重启后跳过
- 跨平台：watchdog 库（macOS FSEvents + Linux inotify + Windows ReadDirectoryChangesW）
"""
from __future__ import annotations

import fnmatch
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty, Queue

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from skill_iter.config import Config
from skill_iter.pipeline import run_single_trajectory
from skill_iter.trajectory import TrajectoryCollector

# 延迟导入避免循环
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from skill_iter.adapters.base import AdapterInterface

logger = logging.getLogger("skill-iter.watcher")


# ---------------------------------------------------------------------------
# 状态持久化
# ---------------------------------------------------------------------------

@dataclass
class WatchState:
    """已处理轨迹的持久化状态。"""
    processed: dict[str, float] = field(default_factory=dict)  # path -> mtime

    @classmethod
    def load(cls, path: Path) -> WatchState:
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(processed=data.get("processed", {}))
        except (json.JSONDecodeError, OSError):
            logger.warning("状态文件损坏，重置: %s", path)
            return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"processed": self.processed}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def is_processed(self, file_path: str, mtime: float) -> bool:
        """检查文件是否已处理（path + mtime 均匹配）。"""
        return self.processed.get(file_path) == mtime

    def mark_processed(self, file_path: str, mtime: float) -> None:
        self.processed[file_path] = mtime


# ---------------------------------------------------------------------------
# watchdog 事件处理器
# ---------------------------------------------------------------------------

class TrajectoryEventHandler(FileSystemEventHandler):
    """监听文件创建和修改事件，匹配 watch_patterns 后入队。"""

    def __init__(self, queue: Queue, patterns: list[str]) -> None:
        super().__init__()
        self._queue = queue
        self._patterns = patterns

    def _matches(self, path: str) -> bool:
        name = os.path.basename(path)
        return any(fnmatch.fnmatch(name, p) for p in self._patterns)

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory and self._matches(event.src_path):
            self._queue.put(event.src_path)

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory and self._matches(event.src_path):
            self._queue.put(event.src_path)


# ---------------------------------------------------------------------------
# Watcher 主类
# ---------------------------------------------------------------------------

class SkillWatcher:
    """文件监听守护进程 — 串行 FIFO 执行演化管线。"""

    def __init__(
        self,
        skill_dir: Path,
        trajectory_dir: Path,
        config: Config,
        *,
        debounce_seconds: float = 2.0,
        adapter: AdapterInterface | None = None,
    ) -> None:
        self.skill_dir = skill_dir
        self.trajectory_dir = trajectory_dir
        self.config = config
        self.debounce_seconds = debounce_seconds
        self._adapter = adapter

        self._state_path = skill_dir / ".watch_state.json"
        self._state = WatchState.load(self._state_path)
        self._queue: Queue[str] = Queue()
        self._observer = Observer()
        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None

        # 去抖缓存：path -> 最后入队时间
        self._debounce_map: dict[str, float] = {}

    def start(self) -> None:
        """启动监听和处理线程，阻塞直到 stop_event 被设置。"""
        handler = TrajectoryEventHandler(self._queue, self.config.watch_patterns)
        self._observer.schedule(handler, str(self.trajectory_dir), recursive=False)
        self._observer.start()

        # 启动前扫描已有文件
        self._scan_existing()

        # 启动 worker 线程
        self._worker_thread = threading.Thread(
            target=self._process_loop, daemon=True, name="watcher-worker",
        )
        self._worker_thread.start()

        # 主线程阻塞等待停止信号
        try:
            while not self._stop_event.is_set():
                self._stop_event.wait(timeout=1.0)
        except KeyboardInterrupt:
            pass

    def stop(self) -> None:
        """停止监听，保存状态。"""
        self._stop_event.set()
        if self._observer.is_alive():
            self._observer.stop()
            self._observer.join(timeout=5.0)
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=5.0)
        self._state.save(self._state_path)
        logger.info("状态已保存: %s", self._state_path)

    def _scan_existing(self) -> None:
        """启动时扫描已有文件，将未处理的入队。"""
        for pattern in self.config.watch_patterns:
            for path in self.trajectory_dir.glob(pattern):
                if path.is_file():
                    self._queue.put(str(path))
        count = self._queue.qsize()
        if count > 0:
            logger.info("扫描到 %d 个已有文件待检查", count)

    def _process_loop(self) -> None:
        """串行消费队列中的文件路径，执行管线。"""
        collector = TrajectoryCollector()

        while not self._stop_event.is_set():
            try:
                file_path = self._queue.get(timeout=1.0)
            except Empty:
                continue

            # 去抖：同一文件短时间内多次触发只处理一次
            now = time.time()
            last = self._debounce_map.get(file_path, 0)
            if now - last < self.debounce_seconds:
                continue
            self._debounce_map[file_path] = now

            path = Path(file_path)
            if not path.exists():
                continue

            # 检查 mtime，跳过已处理
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue

            if self._state.is_processed(str(path), mtime):
                continue

            logger.info("检测到新轨迹: %s", path.name)

            # 解析轨迹
            try:
                traj = collector.parse(path)
            except (ValueError, FileNotFoundError) as e:
                logger.warning("轨迹解析失败 %s: %s", path.name, e)
                # 标记为已处理，避免反复重试
                self._state.mark_processed(str(path), mtime)
                self._state.save(self._state_path)
                continue

            # 执行管线
            result = run_single_trajectory(
                traj, self.skill_dir, self.config,
                adapter=self._adapter,
            )

            if result.success:
                logger.info("演化成功 %s -> %s", path.name, result.patch_id)
            elif result.skip_reason:
                logger.info("跳过 %s: %s", path.name, result.skip_reason)
            else:
                logger.warning("演化失败 %s: %s", path.name, result.error)

            # 标记已处理并持久化
            self._state.mark_processed(str(path), mtime)
            self._state.save(self._state_path)
