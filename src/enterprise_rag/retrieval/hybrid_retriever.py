"""中文：本模块负责实现“混合检索器”相关功能。

English: Orchestrate authorized routing, parallel recall, RRF, reranking, Top-K, and context.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace

from enterprise_rag.core.enums import ErrorCategory
from enterprise_rag.core.exceptions import RetrievalError, error_detail
from enterprise_rag.domain.models import Chunk, RetrievalScope
from enterprise_rag.retrieval.bm25_retriever import BM25Retriever
from enterprise_rag.retrieval.context_builder import ContextBuilder
from enterprise_rag.retrieval.dense_retriever import DenseRetriever
from enterprise_rag.retrieval.dynamic_top_k import DynamicTopK
from enterprise_rag.retrieval.fusion import ReciprocalRankFusion
from enterprise_rag.retrieval.models import EvidenceBundle, RetrievalCandidate, RetrievalQuery
from enterprise_rag.retrieval.query_normalizer import QueryNormalizer
from enterprise_rag.retrieval.reranker import CandidateReranker
from enterprise_rag.retrieval.source_profile_catalog import SourceProfileCatalog
from enterprise_rag.retrieval.source_router import SourceRouter


class HybridRetriever:
    """中文：该类用于表示或实现“混合检索器（HybridRetriever）”的职责。

    English: Execute one complete retrieval round with independent component degradation.
    """

    def __init__(
        self,
        normalizer: QueryNormalizer,
        profiles: SourceProfileCatalog,
        router: SourceRouter,
        dense: DenseRetriever,
        bm25: BM25Retriever,
        fusion: ReciprocalRankFusion,
        reranker: CandidateReranker,
        top_k: DynamicTopK,
        context_builder: ContextBuilder,
        chunk_loader: Callable[[str, Sequence[str]], Sequence[Chunk]],
    ) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store immutable/request-pinned retrieval components and a chunk loader.
        """

        # 中文：变量 `_normalizer` 用于保存“规范化器”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Deterministic query cleaning.
        self._normalizer = normalizer
        # 中文：变量 `_profiles` 用于保存“资料源画像”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: ACL-filtered immutable source profile reader.
        self._profiles = profiles
        # 中文：变量 `_router` 用于保存“路由器”相关数据；其精确定义与约束见下方英文说明。
        # English: Deterministic automatic source router.
        self._router = router
        # 中文：变量 `_dense` 用于保存“稠密向量检索”相关数据；其精确定义与约束见下方英文说明。
        # English: Dense candidate retriever.
        self._dense = dense
        # 中文：变量 `_bm25` 用于保存“BM25 关键词检索”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Lexical candidate retriever.
        self._bm25 = bm25
        # 中文：变量 `_fusion` 用于保存“融合”相关数据；其精确定义与约束见下方英文说明。
        # English: Rank-space fusion component.
        self._fusion = fusion
        # 中文：变量 `_reranker` 用于保存“重排器”相关数据；其精确定义与约束见下方英文说明。
        # English: Optional cross-encoder adapter.
        self._reranker = reranker
        # 中文：变量 `_top_k` 用于保存“Top`k`”相关数据；其精确定义与约束见下方英文说明。
        # English: Explainable evidence-count selector.
        self._top_k = top_k
        # 中文：变量 `_context_builder` 用于保存“上下文构建器”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Prompt-safe context formatter.
        self._context_builder = context_builder
        # 中文：变量 `_chunk_loader` 用于保存“文本块加载器”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Tenant-scoped repository callback loading complete chunk entities.
        self._chunk_loader = chunk_loader

    def retrieve(
        self,
        original_query: str,
        scope: RetrievalScope,
        round_number: int = 1,
    ) -> EvidenceBundle:
        """中文：该函数或方法负责“执行一次检索”相关处理。

        English: Return one bounded evidence bundle or a typed retrieval-system failure.
        """

        # 中文：变量 `query` 用于保存“查询”相关数据；其精确定义与约束见下方英文说明。
        # English: Initial query uses the complete authorized source scope for catalog
        #   routing.
        query = RetrievalQuery(
            original_text=original_query,
            normalized_text=self._normalizer.normalize(original_query),
            scope=scope,
            round_number=round_number,
        )
        # 中文：变量 `routing` 用于保存“路由”相关数据；其精确定义与约束见下方英文说明。
        # English: Router can only choose from ACL-filtered profiles.
        routing = self._router.route(query, self._profiles.profiles(query))
        # 中文：变量 `routed_sources` 用于保存“路由后的资料源”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Routed source IDs are intersected with the original scope defensively.
        routed_sources = frozenset(routing.source_ids) & scope.source_ids
        # 中文：变量 `effective_sources` 用于保存“`effective`资料源”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Empty routing falls back to the original authorized source set.
        effective_sources = routed_sources or scope.source_ids
        routed_scope = replace(scope, source_ids=effective_sources)
        routed_query = replace(query, scope=routed_scope)
        # 中文：本步骤涉及稠密向量检索、BM25 关键词检索、运行，具体约束见下方英文说明。
        # English: Dense and BM25 recall run independently so either can safely degrade.
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="hybrid-retrieval") as executor:
            dense_future = executor.submit(self._dense.retrieve, routed_query)
            bm25_future = executor.submit(self._bm25.retrieve, routed_query)
            # 中文：本步骤涉及结果、错误，具体约束见下方英文说明。
            # English: Results and errors are collected separately.
            dense_candidates, dense_error = _future_result(dense_future)
            bm25_candidates, bm25_error = _future_result(bm25_future)
        if dense_error is not None and bm25_error is not None:
            raise RetrievalError(
                error_detail(
                    "ALL_RETRIEVERS_FAILED",
                    ErrorCategory.RETRIEVAL,
                    "Both dense and lexical retrieval failed.",
                )
            )
        # 中文：变量 `degradations` 用于保存“`degradations`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Degradation labels distinguish system failure from an ordinary empty
        #   result.
        degradations: list[str] = []
        if dense_error is not None:
            degradations.append("dense_unavailable")
        if bm25_error is not None:
            degradations.append("bm25_unavailable")
        # 中文：变量 `fused` 用于保存“`fused`”相关数据；其精确定义与约束见下方英文说明。
        # English: RRF accepts an empty list for a degraded or legitimately empty component.
        fused = self._fusion.fuse(dense_candidates, bm25_candidates)
        # 中文：变量 `loaded_chunks` 用于保存“`loaded`文本块”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Complete chunks are loaded only after fused IDs are known and still
        #   tenant-scoped.
        loaded_chunks = self._chunk_loader(
            scope.tenant_id,
            tuple(candidate.chunk_id for candidate in fused),
        )
        # 中文：变量 `chunks` 用于保存“文本块”相关数据；其精确定义与约束见下方英文说明。
        # English: Mapping supports reranker and Top-K joins without order ambiguity.
        chunks = {chunk.id: chunk for chunk in loaded_chunks}
        reranked, reranker_degraded = self._reranker.rerank(
            routed_query.normalized_text,
            fused,
            chunks,
        )
        if reranker_degraded:
            degradations.append("reranker_unavailable")
        selected, top_k = self._top_k.select(reranked, chunks)
        if scope.index_version_id is None:
            raise ValueError("hybrid retrieval requires a pinned index version")
        return self._context_builder.build(
            index_version_id=scope.index_version_id,
            candidates=selected,
            chunks=chunks,
            routing=routing,
            top_k=top_k,
            degradations=tuple(degradations),
        )


def _future_result(
    future: Future[tuple[RetrievalCandidate, ...]],
) -> tuple[tuple[RetrievalCandidate, ...], Exception | None]:
    """中文：该内部函数负责“异步结果结果”相关处理。

    English: Return a future's tuple result or its exception without conflating empty output.
    """

    try:
        return future.result(), None
    except Exception as exc:
        return (), exc
