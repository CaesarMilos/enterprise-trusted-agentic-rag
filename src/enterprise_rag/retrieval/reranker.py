"""中文：本模块负责实现“重排器”相关功能。

English: Apply an optional cross-encoder while preserving RRF order on provider failure.
"""

from __future__ import annotations

from collections.abc import Mapping

from enterprise_rag.domain.models import Chunk
from enterprise_rag.domain.protocols.models import RerankerProvider
from enterprise_rag.retrieval.models import RetrievalCandidate


class CandidateReranker:
    """中文：该类用于表示或实现“候选项重排器（CandidateReranker）”的职责。

    English: Rerank candidates with chunk text and expose a graceful failure signal.
    """

    def __init__(self, provider: RerankerProvider | None) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store an optional provider selected by configuration.
        """

        # 中文：变量 `_provider` 用于保存“提供方”相关数据；其精确定义与约束见下方英文说明。
        # English: None disables reranking without changing retrieval interfaces.
        self._provider = provider

    def rerank(
        self,
        query: str,
        candidates: tuple[RetrievalCandidate, ...],
        chunks: Mapping[str, Chunk],
    ) -> tuple[tuple[RetrievalCandidate, ...], bool]:
        """中文：该函数或方法负责“重排”相关处理。

        English: Return reranked candidates and whether the provider degraded.
        """

        if self._provider is None or not candidates:
            return candidates, False
        # 中文：变量 `valid_candidates` 用于保存“`valid`候选项”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Missing chunk IDs are excluded before model input and cannot leak
        #   invalid evidence.
        valid_candidates = tuple(
            candidate for candidate in candidates if candidate.chunk_id in chunks
        )
        # 中文：变量 `passages` 用于保存“`passages`”相关数据；其精确定义与约束见下方英文说明。
        # English: Passage order is aligned with valid candidates.
        # 中文：重排输入包含标题路径、编号和 Child 正文，但不会把重复 Parent 全文送入模型。
        # English: Reranking sees headings, identifiers, and child body without repeated parents.
        passages = tuple(chunks[candidate.chunk_id].search_text for candidate in valid_candidates)
        try:
            scores = self._provider.score(query, passages)
            if len(scores) != len(valid_candidates):
                raise ValueError("reranker score count does not match candidate count")
        except Exception:
            # 中文：本步骤涉及安全，具体约束见下方英文说明。
            # English: RRF order is the required safe fallback.
            return candidates, True
        # 中文：变量 `reranked` 用于保存“`reranked`”相关数据；其精确定义与约束见下方英文说明。
        # English: Cross-encoder score becomes the current ordering score while provenance
        #   is retained.
        reranked = tuple(
            RetrievalCandidate(
                chunk_id=candidate.chunk_id,
                score=float(score),
                dense_rank=candidate.dense_rank,
                bm25_rank=candidate.bm25_rank,
                dense_score=candidate.dense_score,
                bm25_score=candidate.bm25_score,
                rerank_score=float(score),
            )
            for candidate, score in zip(valid_candidates, scores, strict=True)
        )
        return (
            tuple(sorted(reranked, key=lambda item: (-item.score, item.chunk_id))),
            False,
        )
