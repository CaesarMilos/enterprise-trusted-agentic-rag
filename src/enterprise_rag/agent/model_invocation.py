"""中文：以向后兼容方式把全局剩余预算传入支持超时参数的模型适配器。

    English: Pass remaining global budget to timeout-aware adapters with compatibility fallback.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping

from enterprise_rag.domain.protocols.models import LLMProvider, ModelResponse


def complete_with_timeout(
    provider: LLMProvider,
    system_prompt: str,
    user_prompt: str,
    metadata: Mapping[str, str] | None,
    timeout_seconds: float | None,
) -> ModelResponse:
    """中文：真实适配器支持时传递子超时；简化测试实现继续使用原协议。

    English: Pass child timeout when supported while preserving simple test providers.
    """

    parameters = inspect.signature(provider.complete).parameters
    if "timeout_seconds" in parameters:
        return provider.complete(
            system_prompt,
            user_prompt,
            metadata,
            timeout_seconds=timeout_seconds,
        )
    return provider.complete(system_prompt, user_prompt, metadata)
