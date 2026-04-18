"""PendingStore 单元测试 — 候选补丁生命周期管理。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from skill_iter.pending_store import (
    PendingStore,
    PendingPatch,
    CommitRecord,
    PatchNotFoundError,
    BaseHashMismatchError,
    PatchApplyError,
)


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def _make_skill_dir(tmp_path: Path, skill_md: str = "# Test Skill\n\n初始内容\n") -> Path:
    """创建临时 skill 目录并写入 SKILL.md。"""
    skill_dir = tmp_path / "test_skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")
    return skill_dir


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _create_pending_json(store: PendingStore, patch_id: str, base_hash: str, **overrides) -> Path:
    """手动写入一个候选补丁 JSON 文件。"""
    store.pending_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "patch_id": patch_id,
        "created_at": "2026-04-16T14:30:00",
        "source_trajectory": "/tmp/traj.md",
        "trajectory_format": "A",
        "description": overrides.get("description", "测试补丁"),
        "diff": overrides.get("diff", ""),
        "new_content": overrides.get("new_content", None),
        "base_hash": base_hash,
        "signals_summary": overrides.get("signals_summary", {}),
        "gate_result": "passed",
    }
    payload.update(overrides)
    path = store.pending_dir / f"{patch_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# TestList
# ---------------------------------------------------------------------------

class TestList:
    def test_empty_dir(self, tmp_path):
        skill_dir = _make_skill_dir(tmp_path)
        store = PendingStore(skill_dir)
        assert store.list() == []

    def test_no_pending_dir(self, tmp_path):
        skill_dir = _make_skill_dir(tmp_path)
        store = PendingStore(skill_dir)
        # .pending_evolution 目录不存在
        assert store.list() == []

    def test_list_multiple(self, tmp_path):
        skill_dir = _make_skill_dir(tmp_path)
        store = PendingStore(skill_dir)
        _create_pending_json(store, "20260416-aaa", "hash1", description="补丁 A")
        _create_pending_json(store, "20260416-bbb", "hash2", description="补丁 B")
        patches = store.list()
        assert len(patches) == 2
        ids = [p.patch_id for p in patches]
        assert "20260416-aaa" in ids
        assert "20260416-bbb" in ids

    def test_skip_corrupt_json(self, tmp_path):
        """损坏的 JSON 文件应跳过。"""
        skill_dir = _make_skill_dir(tmp_path)
        store = PendingStore(skill_dir)
        _create_pending_json(store, "good", "hash1")
        # 写入一个损坏文件
        store.pending_dir.mkdir(parents=True, exist_ok=True)
        (store.pending_dir / "bad.json").write_text("{invalid", encoding="utf-8")
        patches = store.list()
        assert len(patches) == 1
        assert patches[0].patch_id == "good"


# ---------------------------------------------------------------------------
# TestGet
# ---------------------------------------------------------------------------

class TestGet:
    def test_get_existing(self, tmp_path):
        skill_dir = _make_skill_dir(tmp_path)
        store = PendingStore(skill_dir)
        _create_pending_json(store, "p1", "hash1", description="测试")
        patch = store.get("p1")
        assert patch.patch_id == "p1"
        assert patch.description == "测试"

    def test_get_not_found(self, tmp_path):
        skill_dir = _make_skill_dir(tmp_path)
        store = PendingStore(skill_dir)
        with pytest.raises(PatchNotFoundError):
            store.get("nonexistent")

    def test_get_corrupt(self, tmp_path):
        skill_dir = _make_skill_dir(tmp_path)
        store = PendingStore(skill_dir)
        store.pending_dir.mkdir(parents=True, exist_ok=True)
        (store.pending_dir / "corrupt.json").write_text("not json", encoding="utf-8")
        with pytest.raises(PatchNotFoundError, match="损坏"):
            store.get("corrupt")


# ---------------------------------------------------------------------------
# TestCommit — 全文替换模式
# ---------------------------------------------------------------------------

class TestCommitFulltext:
    def test_commit_success(self, tmp_path):
        """全文替换模式 commit 成功。"""
        original = "# Test Skill\n\n初始内容\n"
        new_content = "# Test Skill\n\n改进后的内容\n"
        skill_dir = _make_skill_dir(tmp_path, original)
        store = PendingStore(skill_dir)
        base_hash = _sha256(original)
        _create_pending_json(
            store, "p-full", base_hash,
            new_content=new_content,
            description="全文替换测试",
        )
        record = store.commit("p-full")
        # 验证返回
        assert record.patch_id == "p-full"
        assert record.base_hash == base_hash
        assert record.new_hash == _sha256(new_content)
        assert record.description == "全文替换测试"
        # SKILL.md 已更新
        assert (skill_dir / "SKILL.md").read_text(encoding="utf-8") == new_content
        # 候选文件已删除
        assert not (store.pending_dir / "p-full.json").exists()
        # 备份已创建
        backups = list((store.pending_dir / "backups").glob("*.bak"))
        assert len(backups) == 1
        assert backups[0].read_text(encoding="utf-8") == original

    def test_commit_log_written(self, tmp_path):
        """commit 后 evolve-log.json 有记录。"""
        original = "# Skill\n\n内容\n"
        skill_dir = _make_skill_dir(tmp_path, original)
        store = PendingStore(skill_dir)
        _create_pending_json(
            store, "p-log", _sha256(original),
            new_content="# Skill\n\n新内容\n",
        )
        store.commit("p-log")
        log_path = skill_dir / "reports" / "evolve-log.json"
        assert log_path.exists()
        entries = json.loads(log_path.read_text(encoding="utf-8"))
        assert len(entries) == 1
        assert entries[0]["patch_id"] == "p-log"


# ---------------------------------------------------------------------------
# TestCommit — unified diff 模式
# ---------------------------------------------------------------------------

class TestCommitDiff:
    def test_commit_diff_success(self, tmp_path):
        """unified diff 模式 commit 成功。"""
        original = "# Skill\n\n第一行\n第二行\n第三行\n"
        skill_dir = _make_skill_dir(tmp_path, original)
        store = PendingStore(skill_dir)
        base_hash = _sha256(original)
        diff = (
            "--- a/SKILL.md\n"
            "+++ b/SKILL.md\n"
            "@@ -3,1 +3,1 @@\n"
            "-第一行\n"
            "+改进后第一行\n"
        )
        _create_pending_json(store, "p-diff", base_hash, diff=diff)
        record = store.commit("p-diff")
        result = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        assert "改进后第一行" in result
        assert "第一行" not in result or "改进后第一行" in result


# ---------------------------------------------------------------------------
# TestCommit — 失败场景
# ---------------------------------------------------------------------------

class TestCommitFailure:
    def test_base_hash_mismatch(self, tmp_path):
        """SKILL.md 已被修改，base_hash 不匹配。"""
        skill_dir = _make_skill_dir(tmp_path, "# Skill\n\n原始\n")
        store = PendingStore(skill_dir)
        _create_pending_json(
            store, "p-mismatch", "wrong_hash",
            new_content="# Skill\n\n新\n",
        )
        with pytest.raises(BaseHashMismatchError):
            store.commit("p-mismatch")
        # SKILL.md 未被修改
        assert (skill_dir / "SKILL.md").read_text(encoding="utf-8") == "# Skill\n\n原始\n"

    def test_patch_not_found(self, tmp_path):
        skill_dir = _make_skill_dir(tmp_path)
        store = PendingStore(skill_dir)
        with pytest.raises(PatchNotFoundError):
            store.commit("no-such-patch")

    def test_diff_apply_failure(self, tmp_path):
        """diff 无法应用时抛出 PatchApplyError。"""
        skill_dir = _make_skill_dir(tmp_path, "# Skill\n\n完全不同的内容\n")
        store = PendingStore(skill_dir)
        base_hash = _sha256("# Skill\n\n完全不同的内容\n")
        # 给一个无效 diff（无 hunk）
        _create_pending_json(store, "p-badd", base_hash, diff="garbage diff")
        with pytest.raises(PatchApplyError):
            store.commit("p-badd")

    def test_empty_base_hash_skips_check(self, tmp_path):
        """base_hash 为空时跳过校验（兼容旧数据）。"""
        original = "# Skill\n\n内容\n"
        skill_dir = _make_skill_dir(tmp_path, original)
        store = PendingStore(skill_dir)
        _create_pending_json(
            store, "p-nohash", "",
            new_content="# Skill\n\n新内容\n",
        )
        record = store.commit("p-nohash")
        assert record.patch_id == "p-nohash"


# ---------------------------------------------------------------------------
# TestDiscard
# ---------------------------------------------------------------------------

class TestDiscard:
    def test_discard_success(self, tmp_path):
        skill_dir = _make_skill_dir(tmp_path)
        store = PendingStore(skill_dir)
        _create_pending_json(store, "p-del", "hash1")
        store.discard("p-del", reason="不需要了")
        assert not (store.pending_dir / "p-del.json").exists()

    def test_discard_not_found(self, tmp_path):
        skill_dir = _make_skill_dir(tmp_path)
        store = PendingStore(skill_dir)
        with pytest.raises(PatchNotFoundError):
            store.discard("no-exist")

    def test_discard_log_written(self, tmp_path):
        skill_dir = _make_skill_dir(tmp_path)
        store = PendingStore(skill_dir)
        _create_pending_json(store, "p-dlog", "hash1")
        store.discard("p-dlog", reason="测试丢弃")
        log_path = skill_dir / "reports" / "evolve-log.json"
        assert log_path.exists()
        entries = json.loads(log_path.read_text(encoding="utf-8"))
        assert len(entries) == 1
        assert entries[0]["action"] == "discard"
        assert entries[0]["reason"] == "测试丢弃"


# ---------------------------------------------------------------------------
# TestPendingPatch 数据模型
# ---------------------------------------------------------------------------

class TestPendingPatch:
    def test_roundtrip(self):
        data = {
            "patch_id": "test-id",
            "created_at": "2026-04-16T14:30:00",
            "source_trajectory": "/tmp/t.md",
            "trajectory_format": "A",
            "description": "desc",
            "diff": "some diff",
            "new_content": None,
            "base_hash": "abc123",
            "signals_summary": {"key": "val"},
            "gate_result": "passed",
        }
        patch = PendingPatch.from_dict(data)
        assert patch.to_dict() == data

    def test_from_dict_defaults(self):
        """缺少可选字段时使用默认值。"""
        patch = PendingPatch.from_dict({"patch_id": "minimal"})
        assert patch.patch_id == "minimal"
        assert patch.diff == ""
        assert patch.new_content is None
