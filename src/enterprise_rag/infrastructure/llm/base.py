"""中文：本模块负责实现“基础”相关功能。

English: Provide shared helpers for OpenAI-compatible language-model adapters.
"""

from __future__ import annotations

from collections.abc import Mapping


def safe_metadata(metadata: Mapping[str, str] | None) -> dict[str, str]:
    """中文：该函数或方法负责“安全元数据”相关处理。

    English: Keep only short non-secret metadata values suitable for provider requests.
    """

    if metadata is None:
        return {}
    # 中文：本步骤涉及受限、提示词，具体约束见下方英文说明。
    # English: Keys and values are bounded to avoid accidental prompt or secret propagation.
    return {
        str(key)[:64]: str(value)[:256]
        for key, value in metadata.items()
        if "key" not in str(key).lower() and "token" not in str(key).lower()
    }
