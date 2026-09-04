"""中文：本模块负责实现“模型”相关功能。

English: Define immutable query, candidate, routing, selection, and evidence models.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from enterprise_rag.domain.models import Chunk, RetrievalScope


@dataclass(frozen=True, slots=True)
class RetrievalQuery:
    """中文：该类用于表示或实现“检索查询（RetrievalQuery）”的职责。

    English: Represent one normalized query pinned to an exact authorized index scope.
    """

    # 中文：变量 `original_text` 用于保存“原始文本”相关数据；其精确定义与约束见下方英文说明。
    # English: Original user question retained for answer generation.
    original_text: str
    # 中文：变量 `normalized_text` 用于保存“`normalized`文本”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Deterministically normalized search text.
    normalized_text: str
    # 中文：变量 `scope` 用于保存“范围”相关数据；其精确定义与约束见下方英文说明。
    # English: Exact pre-search authorization and index version.
    scope: RetrievalScope
    # 中文：变量 `round_number` 用于保存“`round``number`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: One-based retrieval attempt number.
    round_number: int = 1


@dataclass(frozen=True, slots=True)
class RetrievalCandidate:
    """中文：该类用于表示或实现“检索候选项（RetrievalCandidate）”的职责。

    English: Represent one chunk candidate as it moves through fusion and reranking.
    """

    # 中文：变量 `chunk_id` 用于保存“文本块标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable deterministic chunk identifier.
    chunk_id: str
    # 中文：变量 `score` 用于保存“计算相关性分数”相关数据；其精确定义与约束见下方英文说明。
    # English: Fused or reranked score used by the current stage.
    score: float
    # 中文：变量 `dense_rank` 用于保存“稠密向量检索`rank`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: One-based rank in the dense result, when present.
    dense_rank: int | None = None
    # 中文：变量 `bm25_rank` 用于保存“BM25 关键词检索`rank`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: One-based rank in the BM25 result, when present.
    bm25_rank: int | None = None
    # 中文：变量 `dense_score` 用于保存“稠密向量检索`score`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Dense similarity retained only for trace diagnostics.
    dense_score: float | None = None
    # 中文：变量 `bm25_score` 用于保存“BM25 关键词检索`score`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: BM25 score retained only for trace diagnostics.
    bm25_score: float | None = None
    # 中文：变量 `rerank_score` 用于保存“重排`score`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Optional cross-encoder score.
    rerank_score: float | None = None


@dataclass(frozen=True, slots=True)
class RoutingResult:
    """中文：该类用于表示或实现“路由结果（RoutingResult）”的职责。

    English: Describe selected knowledge sources and the deterministic routing rationale.
    """

    # 中文：变量 `source_ids` 用于保存“资料源标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Sources selected from the caller's already-authorized scope.
    source_ids: tuple[str, ...]
    # 中文：变量 `mode` 用于保存“`mode`”相关数据；其精确定义与约束见下方英文说明。
    # English: Routing mode: single_source, multi_source, or authorized_global.
    mode: str
    # 中文：变量 `reason` 用于保存“原因”相关数据；其精确定义与约束见下方英文说明。
    # English: Short safe rationale included in traces.
    reason: str
    # 中文：变量 `scores` 用于保存“`scores`”相关数据；其精确定义与约束见下方英文说明。
    # English: Per-source routing relevance scores.
    scores: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TopKDecision:
    """中文：该类用于表示或实现“TopK 值决策（TopKDecision）”的职责。

    English: Describe the evidence count selected within score and token constraints.
    """

    # 中文：变量 `selected_k` 用于保存“选中的`k`”相关数据；其精确定义与约束见下方英文说明。
    # English: Final selected candidate count.
    selected_k: int
    # 中文：变量 `reason` 用于保存“原因”相关数据；其精确定义与约束见下方英文说明。
    # English: Short deterministic explanation of the count.
    reason: str
    # 中文：变量 `dropped_chunk_ids` 用于保存“`dropped`文本块标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Chunk IDs removed by deduplication or budget enforcement.
    dropped_chunk_ids: tuple[str, ...] = ()
    # 中文：按预算实际展开的 Parent ID，用于 Trace 解释证据上下文来源。
    # English: Parent IDs actually expanded within budget for trace explainability.
    expanded_parent_chunk_ids: tuple[str, ...] = ()
    # 中文：最终 Evidence Pack 的估算 Token 数，而非仅 Child 选择阶段的数量。
    # English: Estimated final Evidence Pack tokens after parent expansion.
    final_context_tokens: int = 0
    # 中文：最终候选至少命中一次的 required Need，用于 Trace 和评测。
    # English: Required needs with at least one selected lexical/anchor candidate.
    covered_need_ids: tuple[str, ...] = ()
    # 中文：在候选或 Token 预算中仍未覆盖的 required Need。
    # English: Required needs still uncovered by candidates or the token budget.
    uncovered_need_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    """中文：该类用于表示或实现“证据项目（EvidenceItem）”的职责。

    English: Represent one citable chunk selected for the answer context.
    """

    # 中文：变量 `citation_id` 用于保存“引用标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable display citation label such as C1.
    citation_id: str
    # 中文：变量 `chunk` 用于保存“文本块”相关数据；其精确定义与约束见下方英文说明。
    # English: Complete authorized immutable chunk.
    chunk: Chunk
    # 中文：变量 `score` 用于保存“计算相关性分数”相关数据；其精确定义与约束见下方英文说明。
    # English: Final retrieval relevance score.
    score: float
    # 中文：`context_chunk` 可为更完整 Parent；`chunk` 始终保持精确可引用 Child。
    # English: `context_chunk` may be a parent; `chunk` always remains the precise citable child.
    context_chunk: Chunk | None = None


@dataclass(frozen=True, slots=True)
class RankedCandidateTrace:
    """中文：保存某一真实检索阶段的 Chunk ID、排名和分数。

    English: Store chunk identity, rank, and score from one actual retrieval stage.
    """

    chunk_id: str
    rank: int
    score: float


@dataclass(frozen=True, slots=True)
class RetrievalTrace:
    """中文：按层保存 Router、Dense、BM25、RRF、Rerank 和最终选择的真实输出。

    English: Preserve real stage outputs for router, dense, BM25, RRF, rerank, and selection.
    """

    routed_source_ids: tuple[str, ...] = ()
    dense: tuple[RankedCandidateTrace, ...] = ()
    bm25: tuple[RankedCandidateTrace, ...] = ()
    fused: tuple[RankedCandidateTrace, ...] = ()
    reranked: tuple[RankedCandidateTrace, ...] = ()
    selected: tuple[RankedCandidateTrace, ...] = ()
    parent_context_by_child: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class EvidenceBundle:
    """中文：该类用于表示或实现“证据集合包（EvidenceBundle）”的职责。

    English: Represent the complete bounded context supplied to evidence grading and answering.
    """

    # 中文：变量 `index_version_id` 用于保存“索引版本标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Immutable index snapshot shared by all evidence items.
    index_version_id: str
    # 中文：变量 `items` 用于保存“`items`”相关数据；其精确定义与约束见下方英文说明。
    # English: Ordered citable evidence items.
    items: tuple[EvidenceItem, ...]
    # 中文：变量 `context_text` 用于保存“上下文文本”相关数据；其精确定义与约束见下方英文说明。
    # English: Prompt-ready context with explicit untrusted-document delimiters.
    context_text: str
    # 中文：变量 `token_count` 用于保存“词元`count`”相关数据；其精确定义与约束见下方英文说明。
    # English: Total deterministic context token estimate.
    token_count: int
    # 中文：变量 `routing` 用于保存“路由”相关数据；其精确定义与约束见下方英文说明。
    # English: Source routing decision.
    routing: RoutingResult
    # 中文：变量 `top_k` 用于保存“Top`k`”相关数据；其精确定义与约束见下方英文说明。
    # English: Dynamic Top-K decision.
    top_k: TopKDecision
    # 中文：变量 `degradations` 用于保存“`degradations`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Safe labels describing component degradation.
    degradations: tuple[str, ...] = ()
    # 中文：分层 Trace 只保存 ID/排名/分数，不复制原文或 Prompt。
    # English: Stage trace stores IDs/ranks/scores without copying source text or prompts.
    retrieval_trace: RetrievalTrace | None = None
