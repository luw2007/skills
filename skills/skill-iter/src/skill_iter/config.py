"""配置管理模块。

优先级: CLI overrides > 环境变量 SKILL_ITER_* > pyproject.toml [tool.skill-iter] > 默认值
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field, fields
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10
        import tomli as tomllib  # type: ignore[no-redef]

_ENV_PREFIX = "SKILL_ITER_"


@dataclass
class Config:
    llm_model: str = "anthropic/claude-sonnet-4-20250514"
    llm_base_url: str = ""
    max_trajectory_tokens: int = 16000
    max_patch_lines: int = 50
    pending_dir: str = ".pending_evolution"
    watch_patterns: list[str] = field(default_factory=lambda: ["*.md", "*.json", "*.jsonl"])
    adapter: str = "none"


def _read_pyproject(skill_dir: Path) -> dict:
    """从 skill_dir/pyproject.toml 读取 [tool.skill-iter] 段。"""
    toml_path = skill_dir / "pyproject.toml"
    if not toml_path.is_file():
        return {}
    with open(toml_path, "rb") as f:
        data = tomllib.load(f)
    return data.get("tool", {}).get("skill-iter", {})


def _coerce(value: str, target_type: type) -> object:
    """将环境变量字符串转换为目标类型。"""
    if target_type is bool:
        return value.lower() in ("1", "true", "yes")
    if target_type is int:
        return int(value)
    if target_type is float:
        return float(value)
    return value


def _read_env() -> dict:
    """读取 SKILL_ITER_* 环境变量，key 转为小写字段名。"""
    valid_names = {f.name for f in fields(Config)}
    result: dict = {}
    for key, value in os.environ.items():
        if not key.startswith(_ENV_PREFIX):
            continue
        field_name = key[len(_ENV_PREFIX) :].lower()
        if field_name not in valid_names:
            continue
        result[field_name] = value
    return result


def load_config(skill_dir: Path, overrides: dict | None = None) -> Config:
    """加载并合并配置，返回 Config 实例。

    合并优先级: CLI overrides > 环境变量 > pyproject.toml > dataclass 默认值
    """
    # 1. pyproject.toml
    toml_vals = _read_pyproject(skill_dir)

    # 2. 环境变量
    env_vals = _read_env()

    # 3. 合并: toml -> env -> cli overrides
    merged: dict = {**toml_vals, **env_vals, **(overrides or {})}

    # 4. 类型强转：对 dataclass 字段做类型对齐
    type_map = {f.name: f.type for f in fields(Config)}
    kwargs: dict = {}
    for name, value in merged.items():
        if name not in type_map:
            continue
        expected = type_map[name]
        # 环境变量传入的是 str，需要转换为目标基本类型
        if isinstance(value, str) and expected in ("int", "float", "bool"):
            builtin = {"int": int, "float": float, "bool": bool}[expected]
            value = _coerce(value, builtin)
        kwargs[name] = value

    return Config(**kwargs)
