"""中文：兼容调用支持或尚未支持 timeout 参数的向量与重排 Provider。

English: Compatibly invoke embedding and reranking providers with optional timeout support.
"""

from __future__ import annotations

import inspect
from collections.abc import Sequence

from enterprise_rag.domain.protocols.models import EmbeddingProvider, RerankerProvider


def embed_with_timeout(
    provider: EmbeddingProvider,
    texts: Sequence[str],
    timeout_seconds: float | None,
) -> Sequence[Sequence[float]]:
    """中文：Provider 声明超时参数时下推预算，否则兼容调用旧实现。

    English: Pass the timeout to capable providers and preserve legacy implementations.
    """

    if "timeout_seconds" in inspect.signature(provider.embed).parameters:
        return provider.embed(texts, timeout_seconds=timeout_seconds)
    return provider.embed(texts)


def rerank_with_timeout(
    provider: RerankerProvider,
    query: str,
    passages: Sequence[str],
    timeout_seconds: float | None,
) -> Sequence[float]:
    """中文：Provider 声明超时参数时下推预算，否则兼容调用旧实现。

    English: Pass the timeout to capable providers and preserve legacy implementations.
    """

    if "timeout_seconds" in inspect.signature(provider.score).parameters:
        return provider.score(query, passages, timeout_seconds=timeout_seconds)
    return provider.score(query, passages)
