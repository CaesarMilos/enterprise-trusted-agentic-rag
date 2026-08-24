"""中文：本模块负责实现“向量嵌入包的公共导出”相关功能。

English: Expose local and OpenAI-compatible embedding provider adapters.
"""

from enterprise_rag.infrastructure.embeddings.api_provider import APIEmbeddingProvider
from enterprise_rag.infrastructure.embeddings.local_provider import LocalEmbeddingProvider

__all__ = ["APIEmbeddingProvider", "LocalEmbeddingProvider"]
