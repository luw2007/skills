"""Adapter 注册/加载机制。

通过 adapter 名称加载对应实现：
- "none"  → NullAdapter（空操作，默认）
- "log"   → LogAdapter（日志记录，开发调试用）
- 自定义  → 通过 entry_points "skill_iter.adapters" 发现
"""
from __future__ import annotations

import importlib.metadata
import logging
from typing import Type

from skill_iter.adapters.base import AdapterInterface

logger = logging.getLogger("skill-iter.adapter")

# 内置 adapter 注册表
_BUILTIN_REGISTRY: dict[str, str] = {
    "none": "skill_iter.adapters.null:NullAdapter",
    "log": "skill_iter.adapters.log_adapter:LogAdapter",
}

# 运行时动态注册表（供第三方或测试使用）
_RUNTIME_REGISTRY: dict[str, Type[AdapterInterface]] = {}


def register(name: str, cls: Type[AdapterInterface]) -> None:
    """运行时注册一个 adapter 类。供第三方扩展或测试 mock 使用。"""
    _RUNTIME_REGISTRY[name] = cls


def unregister(name: str) -> None:
    """运行时移除一个已注册的 adapter。"""
    _RUNTIME_REGISTRY.pop(name, None)


def _load_class(dotted_path: str) -> Type[AdapterInterface]:
    """从 'module:ClassName' 格式加载类。"""
    module_path, _, class_name = dotted_path.rpartition(":")
    if not module_path or not class_name:
        raise ValueError(f"adapter 路径格式错误（需要 'module:Class'）: {dotted_path}")
    import importlib
    mod = importlib.import_module(module_path)
    cls = getattr(mod, class_name)
    if not (isinstance(cls, type) and issubclass(cls, AdapterInterface)):
        raise TypeError(f"{dotted_path} 不是 AdapterInterface 的子类")
    return cls


def _discover_entry_points() -> dict[str, str]:
    """通过 entry_points 发现外部注册的 adapter。"""
    result: dict[str, str] = {}
    try:
        eps = importlib.metadata.entry_points()
        # Python 3.12+ 返回 SelectableGroups，3.10-3.11 返回 dict
        if hasattr(eps, "select"):
            selected = eps.select(group="skill_iter.adapters")
        else:
            selected = eps.get("skill_iter.adapters", [])
        for ep in selected:
            result[ep.name] = f"{ep.value}"
    except Exception:
        logger.debug("entry_points 发现失败，忽略", exc_info=True)
    return result


def load_adapter(name: str, config: dict | None = None) -> AdapterInterface:
    """根据名称加载并初始化 adapter 实例。

    查找顺序：运行时注册表 → 内置注册表 → entry_points
    """
    config = config or {}

    # 1. 运行时注册表
    if name in _RUNTIME_REGISTRY:
        instance = _RUNTIME_REGISTRY[name]()
        instance.on_init(config)
        return instance

    # 2. 内置注册表
    if name in _BUILTIN_REGISTRY:
        cls = _load_class(_BUILTIN_REGISTRY[name])
        instance = cls()
        instance.on_init(config)
        return instance

    # 3. entry_points
    ep_registry = _discover_entry_points()
    if name in ep_registry:
        cls = _load_class(ep_registry[name])
        instance = cls()
        instance.on_init(config)
        return instance

    raise ValueError(
        f"未知 adapter: {name!r}。"
        f"可用: {sorted(set(_BUILTIN_REGISTRY) | set(_RUNTIME_REGISTRY) | set(ep_registry))}"
    )


__all__ = [
    "AdapterInterface",
    "load_adapter",
    "register",
    "unregister",
]
