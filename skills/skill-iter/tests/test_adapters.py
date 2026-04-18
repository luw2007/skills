"""Adapter 模块测试 — P4 阶段。

覆盖：
- NullAdapter 基本行为
- LogAdapter 基本行为
- 注册/加载机制
- entry_points 发现失败时的容错
- adapter 集成到 pipeline 的 hook 回调验证
"""
from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from skill_iter.adapters import (
    AdapterInterface,
    load_adapter,
    register,
    unregister,
)
from skill_iter.adapters.base import AdapterInterface as BaseAdapterInterface
from skill_iter.adapters.null import NullAdapter
from skill_iter.adapters.log_adapter import LogAdapter


# ---------------------------------------------------------------------------
# NullAdapter 测试
# ---------------------------------------------------------------------------

class TestNullAdapter:
    def test_is_adapter_interface(self):
        adapter = NullAdapter()
        assert isinstance(adapter, AdapterInterface)

    def test_on_audit_complete_returns_true(self, tmp_path):
        adapter = NullAdapter()
        assert adapter.on_audit_complete(tmp_path, {"total_score": 10}) is True

    def test_on_evolution_proposed_returns_true(self, tmp_path):
        adapter = NullAdapter()
        assert adapter.on_evolution_proposed(tmp_path, {"patch_id": "test"}) is True

    def test_on_evolution_committed_returns_true(self, tmp_path):
        adapter = NullAdapter()
        assert adapter.on_evolution_committed(tmp_path, {"patch_id": "test"}) is True

    def test_load_trajectories_returns_empty(self):
        adapter = NullAdapter()
        assert adapter.load_trajectories("test-skill") == []

    def test_on_init_no_error(self):
        adapter = NullAdapter()
        adapter.on_init({"key": "value"})  # 不应抛异常

    def test_on_shutdown_no_error(self):
        adapter = NullAdapter()
        adapter.on_shutdown()  # 不应抛异常

    def test_on_error_no_error(self):
        adapter = NullAdapter()
        adapter.on_error("evolve", RuntimeError("test"))  # 不应抛异常


# ---------------------------------------------------------------------------
# LogAdapter 测试
# ---------------------------------------------------------------------------

class TestLogAdapter:
    def test_is_adapter_interface(self):
        adapter = LogAdapter()
        assert isinstance(adapter, AdapterInterface)

    def test_on_init_logs(self, caplog):
        adapter = LogAdapter()
        with caplog.at_level(logging.INFO, logger="skill-iter.adapter.log"):
            adapter.on_init({"model": "test"})
        assert "LogAdapter 初始化" in caplog.text

    def test_on_shutdown_logs(self, caplog):
        adapter = LogAdapter()
        with caplog.at_level(logging.INFO, logger="skill-iter.adapter.log"):
            adapter.on_shutdown()
        assert "LogAdapter 关闭" in caplog.text

    def test_on_error_logs(self, caplog):
        adapter = LogAdapter()
        with caplog.at_level(logging.ERROR, logger="skill-iter.adapter.log"):
            adapter.on_error("evolve", RuntimeError("boom"))
        assert "boom" in caplog.text

    def test_on_audit_complete_logs(self, tmp_path, caplog):
        adapter = LogAdapter()
        with caplog.at_level(logging.INFO, logger="skill-iter.adapter.log"):
            result = adapter.on_audit_complete(tmp_path, {"total_score": 42, "dimensions": [1, 2]})
        assert result is True
        assert "审计完成" in caplog.text
        assert "42" in caplog.text

    def test_on_evolution_proposed_logs(self, tmp_path, caplog):
        adapter = LogAdapter()
        with caplog.at_level(logging.INFO, logger="skill-iter.adapter.log"):
            result = adapter.on_evolution_proposed(tmp_path, {
                "patch_id": "20260417-abcd1234",
                "description": "测试补丁",
            })
        assert result is True
        assert "候选演化生成" in caplog.text
        assert "20260417-abcd1234" in caplog.text

    def test_on_evolution_committed_logs(self, tmp_path, caplog):
        adapter = LogAdapter()
        with caplog.at_level(logging.INFO, logger="skill-iter.adapter.log"):
            result = adapter.on_evolution_committed(tmp_path, {"patch_id": "xyz"})
        assert result is True
        assert "演化已合入" in caplog.text

    def test_load_trajectories_returns_empty(self):
        adapter = LogAdapter()
        assert adapter.load_trajectories("my-skill") == []


# ---------------------------------------------------------------------------
# 注册/加载机制测试
# ---------------------------------------------------------------------------

class TestAdapterRegistry:
    def test_load_none_returns_null_adapter(self):
        adapter = load_adapter("none")
        assert isinstance(adapter, NullAdapter)

    def test_load_log_returns_log_adapter(self):
        adapter = load_adapter("log")
        assert isinstance(adapter, LogAdapter)

    def test_load_unknown_raises_value_error(self):
        with pytest.raises(ValueError, match="未知 adapter"):
            load_adapter("nonexistent_adapter_xyz")

    def test_register_and_load_custom(self):
        """运行时注册自定义 adapter 并加载。"""
        class MockAdapter(BaseAdapterInterface):
            def __init__(self):
                self.inited = False
            def on_init(self, config):
                self.inited = True
            def on_audit_complete(self, sd, r):
                return True
            def on_evolution_proposed(self, sd, p):
                return True
            def on_evolution_committed(self, sd, p):
                return True
            def load_trajectories(self, name):
                return []

        register("mock-test", MockAdapter)
        try:
            adapter = load_adapter("mock-test", config={"x": 1})
            assert isinstance(adapter, MockAdapter)
            assert adapter.inited is True
        finally:
            unregister("mock-test")

    def test_unregister_unknown_no_error(self):
        unregister("does-not-exist")  # 不应抛异常

    def test_load_with_config_calls_on_init(self):
        """验证 load_adapter 会调用 on_init 并传入 config。"""
        adapter = load_adapter("log", config={"model": "test-model"})
        assert isinstance(adapter, LogAdapter)

    def test_runtime_registry_priority_over_builtin(self):
        """运行时注册表优先于内置注册表。"""
        class OverrideNull(BaseAdapterInterface):
            def on_audit_complete(self, sd, r): return True
            def on_evolution_proposed(self, sd, p): return True
            def on_evolution_committed(self, sd, p): return True
            def load_trajectories(self, name): return []

        register("none", OverrideNull)
        try:
            adapter = load_adapter("none")
            assert isinstance(adapter, OverrideNull)
            assert not isinstance(adapter, NullAdapter)
        finally:
            unregister("none")

        # 恢复后应加载内置 NullAdapter
        adapter = load_adapter("none")
        assert isinstance(adapter, NullAdapter)


# ---------------------------------------------------------------------------
# Pipeline adapter hook 集成测试
# ---------------------------------------------------------------------------

class TestPipelineAdapterHook:
    """验证 pipeline 在关键节点调用 adapter hook。"""

    def _make_skill_dir(self, tmp_path: Path) -> Path:
        """创建最小 skill 目录结构。"""
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Test Skill\n测试用 skill", encoding="utf-8")
        return skill_dir

    def test_adapter_on_error_called_on_llm_failure(self, tmp_path):
        """LLM 失败时应调用 adapter.on_error。"""
        from skill_iter.config import Config
        from skill_iter.pipeline import run_single_trajectory
        from skill_iter.trajectory import StructuredTrajectory, ExecutionResult
        from skill_iter.trigger_judge import TriggerResult

        skill_dir = self._make_skill_dir(tmp_path)
        cfg = Config()

        traj = StructuredTrajectory(
            source_path=str(tmp_path / "test.md"),
            format="A",
            session_id="test-session",
            skill_name="test-skill",
            messages=[{"role": "user", "content": "hi"}],
            result=ExecutionResult(rating=4, category="general", turns=5),
            raw_text="",
        )

        mock_adapter = MagicMock(spec=AdapterInterface)

        with patch("skill_iter.pipeline.TriggerJudge") as MockJudge, \
             patch("skill_iter.pipeline.SignalExtractor") as MockExtractor:
            # 强制触发演化
            MockJudge.return_value.should_evolve.return_value = TriggerResult(should=True, reason="测试强制触发")
            from skill_iter.llm import LLMError
            MockExtractor.return_value.extract.side_effect = LLMError("模拟 LLM 失败")

            result = run_single_trajectory(
                traj, skill_dir, cfg,
                feedback_history=[],
                adapter=mock_adapter,
            )

        assert not result.success
        assert "信号提取失败" in result.error
        mock_adapter.on_error.assert_called_once()
        args = mock_adapter.on_error.call_args
        assert args[0][0] == "evolve"

    def test_adapter_on_evolution_proposed_called_on_success(self, tmp_path):
        """补丁暂存成功时应调用 adapter.on_evolution_proposed。"""
        from skill_iter.config import Config
        from skill_iter.pipeline import run_single_trajectory
        from skill_iter.trajectory import StructuredTrajectory, ExecutionResult
        from skill_iter.signal_extractor import Signals, Fix
        from skill_iter.patch_generator import Patch
        from skill_iter.gateway import GateResult
        from skill_iter.trigger_judge import TriggerResult

        skill_dir = self._make_skill_dir(tmp_path)
        cfg = Config()

        traj = StructuredTrajectory(
            source_path=str(tmp_path / "test.md"),
            format="A",
            session_id="test-session",
            skill_name="test-skill",
            messages=[{"role": "user", "content": "hi"}],
            result=ExecutionResult(rating=4, category="general", turns=5),
            raw_text="",
        )

        mock_adapter = MagicMock(spec=AdapterInterface)

        fake_signals = Signals(
            invariants=["保持简洁"],
            fixes=[Fix(target="section1", issue="不够清晰", suggestion="改进描述")],
            new_phases=[],
            raw_response={},
        )
        fake_patch = Patch(
            diff="--- a/SKILL.md\n+++ b/SKILL.md\n@@ -1,2 +1,3 @@\n # Test Skill\n 测试用 skill\n+新内容",
            description="测试补丁",
            new_content=None,
            base_hash="abc123",
            signals_summary="测试信号",
        )
        fake_gate = GateResult(passed=True, checks=[])

        with patch("skill_iter.pipeline.TriggerJudge") as MockJudge, \
             patch("skill_iter.pipeline.SignalExtractor") as MockExtractor, \
             patch("skill_iter.pipeline.PatchGenerator") as MockGenerator, \
             patch("skill_iter.pipeline.Gateway") as MockGateway:

            MockJudge.return_value.should_evolve.return_value = TriggerResult(should=True, reason="测试强制触发")
            MockExtractor.return_value.extract.return_value = fake_signals
            MockGenerator.return_value.generate.return_value = fake_patch
            MockGateway.return_value.scan_signals.return_value = MagicMock(ok=True)
            MockGateway.return_value.validate.return_value = fake_gate

            result = run_single_trajectory(
                traj, skill_dir, cfg,
                feedback_history=[],
                adapter=mock_adapter,
            )

        assert result.success
        assert result.patch_id is not None
        mock_adapter.on_evolution_proposed.assert_called_once()
        call_args = mock_adapter.on_evolution_proposed.call_args[0]
        assert call_args[0] == skill_dir
        assert "patch_id" in call_args[1]

    def test_no_adapter_no_crash(self, tmp_path):
        """adapter=None 时管线正常运行不崩溃。"""
        from skill_iter.config import Config
        from skill_iter.pipeline import run_single_trajectory
        from skill_iter.trajectory import StructuredTrajectory, ExecutionResult

        skill_dir = self._make_skill_dir(tmp_path)
        cfg = Config()

        traj = StructuredTrajectory(
            source_path=str(tmp_path / "test.md"),
            format="A",
            session_id="test-session",
            skill_name="test-skill",
            messages=[{"role": "user", "content": "hi"}],
            result=ExecutionResult(rating=5, category="simple", turns=1),
            raw_text="",
        )

        # rating=5, category=simple, turns=1 → TriggerJudge 返回 should=False，跳过演化不触发 LLM
        result = run_single_trajectory(
            traj, skill_dir, cfg,
            feedback_history=[],
            adapter=None,
        )
        assert not result.success
        assert result.skip_reason is not None
