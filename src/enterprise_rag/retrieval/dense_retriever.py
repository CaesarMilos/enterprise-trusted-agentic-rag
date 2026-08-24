"""中文：本模块负责实现“稠密向量检索检索器”相关功能。

English: Retrieve permission-filtered dense candidates from one pinned index version.
"""

from __future__ import annotations

from enterprise_rag.domain.protocols.indexes import DenseIndex
from enterprise_rag.indexing.embedding_service import EmbeddingService
from enterprise_rag.retrieval.models import RetrievalCandidate, RetrievalQuery


class DenseRetriever:
    """中文：该类用于表示或实现“稠密向量检索检索器（DenseRetriever）”的职责。

    English: Embed a normalized query and adapt dense results into common candidates.
    """

    def __init__(self, index: DenseIndex, embeddings: EmbeddingService, candidate_k: int) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store the pinned index, embedding service, and bounded candidate count.
        """

        # 中文：变量 `_index` 用于保存“索引”相关数据；其精确定义与约束见下方英文说明。
        # English: Dense index is immutable for the request.
        self._index = index
        # 中文：变量 `_embeddings` 用于保存“向量嵌入”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Embedding service applies the same normalization as index construction.
        self._embeddings = embeddings
        # 中文：变量 `_candidate_k` 用于保存“候选项`k`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Candidate limit controls pre-fusion work.
        self._candidate_k = candidate_k

    def retrieve(self, query: RetrievalQuery) -> tuple[RetrievalCandidate, ...]:
        """中文：该函数或方法负责“执行一次检索”相关处理。

        English: Return dense candidates with one-based ranks.
        """

        # 中文：变量 `query_vector` 用于保存“查询向量”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Query vector uses the configured provider fingerprint matching the
        #   index manifest.
        query_vector = self._embeddings.embed_query(query.normalized_text)
        # 中文：变量 `results` 用于保存“结果”相关数据；其精确定义与约束见下方英文说明。
        # English: Index applies the query's exact ACL scope before returning stable chunk
        #   IDs.
        results = self._index.search(query_vector.tolist(), self._candidate_k, query.scope)
        return tuple(
            RetrievalCandidate(
                chunk_id=chunk_id,
                score=score,
                dense_rank=rank,
                dense_score=score,
            )
            for rank, (chunk_id, score) in enumerate(results, start=1)
        )
