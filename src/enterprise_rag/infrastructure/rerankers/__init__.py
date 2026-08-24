"""中文：本模块负责实现“`rerankers`包的公共导出”相关功能。

English: Expose optional local cross-encoder reranking adapters.
"""

from enterprise_rag.infrastructure.rerankers.cross_encoder import CrossEncoderReranker

__all__ = ["CrossEncoderReranker"]
