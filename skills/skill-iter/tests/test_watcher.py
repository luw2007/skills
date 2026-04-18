"""Watcher 守护进程单元测试。"""
from __future__ import annotations

import json
import time
import threading
from pathlib import Path
from queue import Queue
from unittest.mock import patch, MagicMock

import pytest

from skill_iter.watcher import WatchState, TrajectoryEventHandler, SkillWatcher
from skill_iter.config import Config
from skill_iter.pipeline import PipelineResult


FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# WatchState 状态持久化
# ---------------------------------------------------------------------------

class TestWatchState:
    def test_load_empty(self, tmp_path):
        """不存在的文件应返回空状态。"""
        state = WatchState.load(tmp_path / "nonexistent.json")
        assert state.processed == {}

    def test_save_and_load(self, tmp_path):
        """保存后重新加载应保持一致。"""
        state_path = tmp_path / ".watch_state.json"
        state = WatchState()
        state.mark_processed("/a/b.md", 1234.5)
        state.mark_processed("/c/d.json", 5678.0)
        state.save(state_path)

        loaded = WatchState.load(state_path)
        assert loaded.processed == {"/a/b.md": 1234.5, "/c/d.json": 5678.0}

    def test_is_processed_match(self, tmp_path):
        """path + mtime 完全匹配时返回 True。"""
        state = WatchState()
        state.mark_processed("/test.md", 100.0)
        assert state.is_processed("/test.md", 100.0) is True

    def test_is_processed_mtime_changed(self):
        """mtime 不同时返回 False（文件被修改）。"""
        state = WatchState()
        state.mark_processed("/test.md", 100.0)
        assert state.is_processed("/test.md", 200.0) is False

    def test_is_processed_new_file(self):
        """未记录的文件返回 False。"""
        state = WatchState()
        assert state.is_processed("/new.md", 100.0) is False

    def test_load_corrupt_json(self, tmp_path):
        """损坏的 JSON 文件应返回空状态。"""
        state_path = tmp_path / "bad.json"
        state_path.write_text("NOT JSON", encoding="utf-8")
        state = WatchState.load(state_path)
        assert state.processed == {}

    def test_save_creates_parent_dir(self, tmp_path):
        """save 应自动创建父目录。"""
        nested = tmp_path / "a" / "b" / "state.json"
        state = WatchState()
        state.mark_processed("/x.md", 1.0)
        state.save(nested)
        assert nested.exists()


# ---------------------------------------------------------------------------
# TrajectoryEventHandler 事件匹配
# ---------------------------------------------------------------------------

class TestEventHandler:
    def test_matches_md(self):
        q: Queue = Queue()
        handler = TrajectoryEventHandler(q, ["*.md", "*.json", "*.jsonl"])
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/tmp/session.md"
        handler.on_created(event)
        assert q.qsize() == 1
        assert q.get() == "/tmp/session.md"

    def test_matches_jsonl(self):
        q: Queue = Queue()
        handler = TrajectoryEventHandler(q, ["*.md", "*.json", "*.jsonl"])
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/tmp/output.jsonl"
        handler.on_modified(event)
        assert q.qsize() == 1

    def test_ignores_non_matching(self):
        q: Queue = Queue()
        handler = TrajectoryEventHandler(q, ["*.md"])
        event = MagicMock()
        event.is_directory = False
        event.src_path = "/tmp/data.csv"
        handler.on_created(event)
        assert q.qsize() == 0

    def test_ignores_directory(self):
        q: Queue = Queue()
        handler = TrajectoryEventHandler(q, ["*.md"])
        event = MagicMock()
        event.is_directory = True
        event.src_path = "/tmp/subdir.md"
        handler.on_created(event)
        assert q.qsize() == 0


# ---------------------------------------------------------------------------
# SkillWatcher 集成测试
# ---------------------------------------------------------------------------

class TestSkillWatcher:
    @pytest.fixture
    def skill_env(self, tmp_path):
        """创建 skill_dir + trajectory_dir 环境。"""
        skill_dir = tmp_path / "my_skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Test Skill\n", encoding="utf-8")
        traj_dir = tmp_path / "trajectories"
        traj_dir.mkdir()
        return skill_dir, traj_dir

    def test_scan_existing_files(self, skill_env):
        """启动时应扫描已有的轨迹文件到队列。"""
        skill_dir, traj_dir = skill_env
        # 放一个 fixture 文件
        src = FIXTURES / "sample_format_a.md"
        (traj_dir / "session.md").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

        cfg = Config()
        watcher = SkillWatcher(
            skill_dir=skill_dir,
            trajectory_dir=traj_dir,
            config=cfg,
        )
        watcher._scan_existing()
        assert watcher._queue.qsize() >= 1

    def test_state_persisted_after_process(self, skill_env):
        """处理后 .watch_state.json 应包含已处理的文件。"""
        skill_dir, traj_dir = skill_env
        src = FIXTURES / "sample_format_a.md"
        traj_file = traj_dir / "session.md"
        traj_file.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        mtime = traj_file.stat().st_mtime

        cfg = Config()
        watcher = SkillWatcher(
            skill_dir=skill_dir,
            trajectory_dir=traj_dir,
            config=cfg,
            debounce_seconds=0,  # 测试无需去抖
        )

        # 手动入队并用 mock 管线处理
        watcher._queue.put(str(traj_file))

        with patch("skill_iter.watcher.run_single_trajectory") as mock_run:
            mock_run.return_value = PipelineResult(
                source="session.md", success=True, patch_id="test-001",
            )

            # 用线程跑 process_loop，跑一个然后停
            def run_then_stop():
                time.sleep(0.5)
                watcher._stop_event.set()

            threading.Thread(target=run_then_stop, daemon=True).start()
            watcher._process_loop()

        # 验证状态已持久化
        state = WatchState.load(watcher._state_path)
        assert state.is_processed(str(traj_file), mtime) is True

    def test_skip_already_processed(self, skill_env):
        """已处理的文件不应再次触发管线。"""
        skill_dir, traj_dir = skill_env
        src = FIXTURES / "sample_format_a.md"
        traj_file = traj_dir / "session.md"
        traj_file.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        mtime = traj_file.stat().st_mtime

        cfg = Config()
        watcher = SkillWatcher(
            skill_dir=skill_dir,
            trajectory_dir=traj_dir,
            config=cfg,
            debounce_seconds=0,
        )

        # 预设状态为已处理
        watcher._state.mark_processed(str(traj_file), mtime)
        watcher._queue.put(str(traj_file))

        with patch("skill_iter.watcher.run_single_trajectory") as mock_run:
            mock_run.return_value = PipelineResult(source="session.md", success=True)

            def run_then_stop():
                time.sleep(0.5)
                watcher._stop_event.set()

            threading.Thread(target=run_then_stop, daemon=True).start()
            watcher._process_loop()

            # 已处理的文件不应调用 run_single_trajectory
            mock_run.assert_not_called()

    def test_debounce_filters_rapid_events(self, skill_env):
        """短时间内同一文件多次入队只应处理一次。"""
        skill_dir, traj_dir = skill_env
        src = FIXTURES / "sample_format_a.md"
        traj_file = traj_dir / "session.md"
        traj_file.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

        cfg = Config()
        watcher = SkillWatcher(
            skill_dir=skill_dir,
            trajectory_dir=traj_dir,
            config=cfg,
            debounce_seconds=10.0,  # 大值确保去抖生效
        )

        # 入队 3 次
        for _ in range(3):
            watcher._queue.put(str(traj_file))

        with patch("skill_iter.watcher.run_single_trajectory") as mock_run:
            mock_run.return_value = PipelineResult(
                source="session.md", success=True, patch_id="test-001",
            )

            def run_then_stop():
                time.sleep(1.0)
                watcher._stop_event.set()

            threading.Thread(target=run_then_stop, daemon=True).start()
            watcher._process_loop()

            # 只处理一次（后两次被去抖过滤）
            assert mock_run.call_count == 1

    def test_parse_failure_marks_processed(self, skill_env):
        """解析失败的文件也应标记为已处理，避免反复重试。"""
        skill_dir, traj_dir = skill_env
        bad_file = traj_dir / "bad.md"
        bad_file.write_text("not a valid trajectory", encoding="utf-8")
        mtime = bad_file.stat().st_mtime

        cfg = Config()
        watcher = SkillWatcher(
            skill_dir=skill_dir,
            trajectory_dir=traj_dir,
            config=cfg,
            debounce_seconds=0,
        )
        watcher._queue.put(str(bad_file))

        def run_then_stop():
            time.sleep(0.5)
            watcher._stop_event.set()

        threading.Thread(target=run_then_stop, daemon=True).start()
        watcher._process_loop()

        state = WatchState.load(watcher._state_path)
        assert state.is_processed(str(bad_file), mtime) is True

    def test_stop_saves_state(self, skill_env):
        """stop() 应保存状态到文件。"""
        skill_dir, traj_dir = skill_env
        cfg = Config()
        watcher = SkillWatcher(
            skill_dir=skill_dir,
            trajectory_dir=traj_dir,
            config=cfg,
        )
        watcher._state.mark_processed("/test.md", 99.0)
        watcher._stop_event.set()
        watcher.stop()

        assert watcher._state_path.exists()
        loaded = WatchState.load(watcher._state_path)
        assert loaded.is_processed("/test.md", 99.0) is True
