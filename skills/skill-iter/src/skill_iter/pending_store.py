"""候选补丁管理模块 — PendingStore。

职责：管理 .pending_evolution/ 目录下的候选补丁生命周期。
操作：list / get / commit / discard
关键约束：commit 时校验 base_hash（SKILL.md SHA256 一致性），不一致则拒绝。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------

class PendingStoreError(Exception):
    """PendingStore 操作异常基类。"""


class PatchNotFoundError(PendingStoreError):
    """指定的 patch_id 不存在。"""


class BaseHashMismatchError(PendingStoreError):
    """commit 时 SKILL.md 的 SHA256 与 patch 记录的 base_hash 不一致。"""

    def __init__(self, patch_id: str, expected: str, actual: str) -> None:
        self.patch_id = patch_id
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"base_hash 不一致: patch 记录 {expected[:12]}...，"
            f"当前 SKILL.md {actual[:12]}...。"
            f"SKILL.md 已被修改，请重新生成补丁。"
        )


class PatchApplyError(PendingStoreError):
    """patch 应用失败。"""


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class PendingPatch:
    """候选补丁元数据。"""
    patch_id: str
    created_at: str
    source_trajectory: str
    trajectory_format: str
    description: str
    diff: str
    new_content: str | None
    base_hash: str
    signals_summary: dict
    gate_result: str

    @classmethod
    def from_dict(cls, data: dict) -> PendingPatch:
        return cls(
            patch_id=data["patch_id"],
            created_at=data.get("created_at", ""),
            source_trajectory=data.get("source_trajectory", ""),
            trajectory_format=data.get("trajectory_format", ""),
            description=data.get("description", ""),
            diff=data.get("diff", ""),
            new_content=data.get("new_content"),
            base_hash=data.get("base_hash", ""),
            signals_summary=data.get("signals_summary", {}),
            gate_result=data.get("gate_result", ""),
        )

    def to_dict(self) -> dict:
        return {
            "patch_id": self.patch_id,
            "created_at": self.created_at,
            "source_trajectory": self.source_trajectory,
            "trajectory_format": self.trajectory_format,
            "description": self.description,
            "diff": self.diff,
            "new_content": self.new_content,
            "base_hash": self.base_hash,
            "signals_summary": self.signals_summary,
            "gate_result": self.gate_result,
        }


# ---------------------------------------------------------------------------
# 提交记录
# ---------------------------------------------------------------------------

@dataclass
class CommitRecord:
    """patch 提交记录，写入 evolve-log.json。"""
    patch_id: str
    committed_at: str
    description: str
    base_hash: str
    new_hash: str
    backup_path: str

    def to_dict(self) -> dict:
        return {
            "patch_id": self.patch_id,
            "committed_at": self.committed_at,
            "description": self.description,
            "base_hash": self.base_hash,
            "new_hash": self.new_hash,
            "backup_path": self.backup_path,
        }


# ---------------------------------------------------------------------------
# PendingStore
# ---------------------------------------------------------------------------

class PendingStore:
    """候选补丁管理器。

    管理 skill_dir/.pending_evolution/ 目录下的 JSON 补丁文件。
    """

    def __init__(self, skill_dir: Path, pending_dir_name: str = ".pending_evolution") -> None:
        self.skill_dir = skill_dir.resolve()
        self.pending_dir = self.skill_dir / pending_dir_name
        self.skill_md_path = self.skill_dir / "SKILL.md"

    # ------ 查询 ------

    def list(self) -> list[PendingPatch]:
        """列出所有候选补丁，按创建时间排序。"""
        if not self.pending_dir.is_dir():
            return []
        patches: list[PendingPatch] = []
        for f in sorted(self.pending_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                patches.append(PendingPatch.from_dict(data))
            except (json.JSONDecodeError, KeyError):
                continue
        return patches

    def get(self, patch_id: str) -> PendingPatch:
        """读取指定候选补丁。

        Raises:
            PatchNotFoundError: patch_id 对应文件不存在或不合法
        """
        path = self._patch_path(patch_id)
        if not path.exists():
            raise PatchNotFoundError(f"未找到补丁: {patch_id}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return PendingPatch.from_dict(data)
        except (json.JSONDecodeError, KeyError) as e:
            raise PatchNotFoundError(f"补丁文件损坏: {patch_id} ({e})") from e

    # ------ 提交 ------

    def commit(self, patch_id: str) -> CommitRecord:
        """应用候选补丁到 SKILL.md。

        流程：
        1. 读取候选补丁 JSON
        2. 校验 base_hash 与当前 SKILL.md SHA256 一致
        3. 备份当前 SKILL.md
        4. 应用 patch（全文替换 or unified diff）
        5. 记录提交日志
        6. 删除候选补丁文件

        Raises:
            PatchNotFoundError: patch_id 不存在
            BaseHashMismatchError: SKILL.md 已变更
            PatchApplyError: patch 应用失败
        """
        patch = self.get(patch_id)

        # 1. 读取当前 SKILL.md
        current_md = self._read_skill_md()

        # 2. 校验 base_hash
        current_hash = hashlib.sha256(current_md.encode()).hexdigest()
        if patch.base_hash and current_hash != patch.base_hash:
            raise BaseHashMismatchError(patch_id, patch.base_hash, current_hash)

        # 3. 应用 patch
        new_content = self._apply(patch, current_md)
        if new_content is None:
            raise PatchApplyError(
                f"无法应用补丁 {patch_id}，diff 与当前 SKILL.md 不匹配"
            )

        # 4. 备份
        backup_path = self._backup_skill_md(current_md, patch_id)

        # 5. 写入新 SKILL.md
        self.skill_md_path.write_text(new_content, encoding="utf-8")
        new_hash = hashlib.sha256(new_content.encode()).hexdigest()

        # 6. 记录提交日志
        record = CommitRecord(
            patch_id=patch_id,
            committed_at=datetime.now().isoformat(timespec="seconds"),
            description=patch.description,
            base_hash=patch.base_hash,
            new_hash=new_hash,
            backup_path=str(backup_path),
        )
        self._append_commit_log(record)

        # 7. 删除候选补丁文件
        self._patch_path(patch_id).unlink()

        return record

    # ------ 丢弃 ------

    def discard(self, patch_id: str, reason: str = "") -> None:
        """丢弃候选补丁。

        记录丢弃日志后删除文件。

        Raises:
            PatchNotFoundError: patch_id 不存在
        """
        patch = self.get(patch_id)
        # 记录丢弃日志
        self._append_discard_log(patch, reason)
        # 删除文件
        self._patch_path(patch_id).unlink()

    # ------ 内部方法 ------

    def _patch_path(self, patch_id: str) -> Path:
        return self.pending_dir / f"{patch_id}.json"

    def _read_skill_md(self) -> str:
        """读取当前 SKILL.md 内容。空文件或不存在时返回空字符串。"""
        if not self.skill_md_path.exists():
            return ""
        return self.skill_md_path.read_text(encoding="utf-8")

    @staticmethod
    def _apply(patch: PendingPatch, skill_md: str) -> str | None:
        """应用补丁，返回新内容。失败返回 None。

        优先使用 new_content（全文替换），否则尝试 unified diff。
        """
        if patch.new_content:
            return patch.new_content
        try:
            from skill_iter.gateway import _apply_unified_diff
            return _apply_unified_diff(patch.diff, skill_md)
        except Exception:
            return None

    def _backup_skill_md(self, content: str, patch_id: str) -> Path:
        """备份当前 SKILL.md 到 .pending_evolution/backups/。"""
        backup_dir = self.pending_dir / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = backup_dir / f"SKILL.md.{ts}.{patch_id[:8]}.bak"
        backup_path.write_text(content, encoding="utf-8")
        return backup_path

    def _append_commit_log(self, record: CommitRecord) -> None:
        """追加提交记录到 reports/evolve-log.json。"""
        log_path = self.skill_dir / "reports" / "evolve-log.json"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        entries: list = []
        if log_path.exists():
            try:
                entries = json.loads(log_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                entries = []

        entries.append(record.to_dict())
        # 保留最近 200 条
        entries = entries[-200:]
        log_path.write_text(
            json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _append_discard_log(self, patch: PendingPatch, reason: str) -> None:
        """追加丢弃记录到 reports/evolve-log.json。"""
        log_path = self.skill_dir / "reports" / "evolve-log.json"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        entries: list = []
        if log_path.exists():
            try:
                entries = json.loads(log_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                entries = []

        entries.append({
            "action": "discard",
            "patch_id": patch.patch_id,
            "discarded_at": datetime.now().isoformat(timespec="seconds"),
            "description": patch.description,
            "reason": reason,
        })
        entries = entries[-200:]
        log_path.write_text(
            json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
        )
