"""中文：本模块负责实现“工厂”相关功能。

English: Construct configured provider adapters once during application dependency wiring.
"""

from __future__ import annotations

from enterprise_rag.core.config import LLMSettings
from enterprise_rag.infrastructure.llm.openai_compatible import OpenAICompatibleLLM


def create_llm(settings: LLMSettings) -> OpenAICompatibleLLM:
    """中文：该函数或方法负责“创建大语言模型”相关处理。

    English: Create the supported OpenAI-compatible language-model adapter.
    """

    if settings.provider != "openai-compatible":
        raise ValueError(f"unsupported LLM provider: {settings.provider}")
    return OpenAICompatibleLLM(
        model=settings.model,
        base_url=settings.base_url,
        api_key_env=settings.api_key_env,
        timeout_seconds=settings.request_timeout_seconds,
        temperature=settings.temperature,
    )
