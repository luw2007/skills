"""LLM 调用封装 — 基于 litellm 统一调用，支持 JSON 解析重试和错误处理。"""
from __future__ import annotations

import json
import re


# ---------------------------------------------------------------------------
# 异常定义
# ---------------------------------------------------------------------------

class LLMError(Exception):
    """LLM 调用通用错误。"""


class LLMParseError(LLMError):
    """JSON 解析失败（重试后仍失败）。"""


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*\n([\s\S]*?)\n\s*```")

_FORMAT_HINT = (
    "\n\n请严格输出合法 JSON，不要包含任何 markdown 代码块标记或其他文本。"
    "上次你的输出无法被解析为 JSON。"
)


def _extract_json(text: str) -> dict:
    """尝试从文本中提取 JSON 对象。

    优先 json.loads 整段文本，失败则尝试提取 ```json ... ``` 代码块。

    Raises:
        json.JSONDecodeError: 无法解析
    """
    text = text.strip()

    # 尝试 1: 直接解析
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    # 尝试 2: 提取代码块
    m = _JSON_BLOCK_RE.search(text)
    if m:
        obj = json.loads(m.group(1))
        if isinstance(obj, dict):
            return obj

    # 尝试 3: 找到第一个 { 和最后一个 } 之间的内容
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        obj = json.loads(text[first_brace : last_brace + 1])
        if isinstance(obj, dict):
            return obj

    raise json.JSONDecodeError("未找到合法 JSON 对象", text, 0)


def _call_litellm(
    *,
    model: str,
    system: str,
    user: str,
    base_url: str | None,
) -> str:
    """底层 litellm 调用，返回原始文本。"""
    try:
        import litellm  # 延迟导入，允许在无 litellm 环境下加载模块
    except ImportError as e:
        raise LLMError("litellm 未安装，请执行: pip install litellm") from e

    kwargs: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "num_retries": 3,
    }
    if base_url:
        kwargs["api_base"] = base_url

    try:
        response = litellm.completion(**kwargs)
    except Exception as e:
        err_name = type(e).__name__
        # litellm 认证错误
        if "auth" in err_name.lower() or "authentication" in err_name.lower():
            raise LLMError(
                f"API 认证失败，请检查配置（环境变量或 pyproject.toml 中的 API key）: {e}"
            ) from e
        raise LLMError(f"LLM 调用失败 ({err_name}): {e}") from e

    return response.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------

def call_llm_json(
    *,
    model: str,
    system: str,
    user: str,
    base_url: str | None = None,
    max_retries: int = 2,
) -> dict:
    """调用 LLM 并解析 JSON 响应。

    JSON parse 失败会重试 max_retries 次（强化格式提示）。

    Args:
        model: litellm 格式模型名（如 "anthropic/claude-sonnet-4-20250514"）
        system: 系统提示
        user: 用户提示
        base_url: 自定义 API base URL，None 则用 litellm 默认
        max_retries: JSON 解析失败重试次数

    Returns:
        解析后的 dict

    Raises:
        LLMParseError: JSON 解析失败（重试后仍失败）
        LLMError: 其他 LLM 调用错误
    """
    last_error: Exception | None = None

    for attempt in range(1 + max_retries):
        prompt = user if attempt == 0 else user + _FORMAT_HINT
        text = _call_litellm(model=model, system=system, user=prompt, base_url=base_url)

        try:
            return _extract_json(text)
        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
            continue

    raise LLMParseError(
        f"JSON 解析失败（已重试 {max_retries} 次）: {last_error}"
    )


def call_llm_text(
    *,
    model: str,
    system: str,
    user: str,
    base_url: str | None = None,
) -> str:
    """调用 LLM 返回纯文本响应。

    用于 PatchGenerator 生成 unified diff 等场景。
    """
    return _call_litellm(model=model, system=system, user=user, base_url=base_url)
