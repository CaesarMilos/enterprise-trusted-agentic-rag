"""中文：本模块负责实现“BM25 关键词检索检索器”相关功能。

English: Retrieve permission-filtered lexical candidates from one pinned index version.
"""

from __future__ import annotations

from enterprise_rag.domain.protocols.indexes import BM25Index
from enterprise_rag.retrieval.models import RetrievalCandidate, RetrievalQuery


class BM25Retriever:
    """中文：该类用于表示或实现“BM25 关键词检索检索器（BM25Retriever）”的职责。

    English: Adapt BM25 results into common candidates with one-based ranks.
    """

    def __init__(self, index: BM25Index, candidate_k: int) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store the pinned lexical index and bounded candidate count.
        """

        # 中文：变量 `_index` 用于保存“索引”相关数据；其精确定义与约束见下方英文说明。
        # English: BM25 index is immutable for the request.
        self._index = index
        # 中文：变量 `_candidate_k` 用于保存“候选项`k`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Candidate limit controls pre-fusion work.
        self._candidate_k = candidate_k

    def retrieve(self, query: RetrievalQuery) -> tuple[RetrievalCandidate, ...]:
        """中文：该函数或方法负责“执行一次检索”相关处理。

        English: Return lexical candidates with original scores and ranks.
        """

        # 中文：变量 `results` 用于保存“结果”相关数据；其精确定义与约束见下方英文说明。
        # English: Index applies the exact ACL scope before returning stable chunk IDs.
        results = self._index.search(query.normalized_text, self._candidate_k, query.scope)
        return tuple(
            RetrievalCandidate(
                chunk_id=chunk_id,
                score=score,
                bm25_rank=rank,
                bm25_score=score,
            )
            for rank, (chunk_id, score) in enumerate(results, start=1)
        )
