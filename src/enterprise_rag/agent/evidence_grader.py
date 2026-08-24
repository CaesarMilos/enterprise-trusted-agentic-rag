"""中文：本模块负责实现“证据评估器”相关功能。

English: Grade evidence relevance, coverage, quality, and simple contradiction signals.
"""

from __future__ import annotations

from dataclasses import dataclass

from enterprise_rag.indexing.bm25_index import lexical_tokens
from enterprise_rag.retrieval.identifier_normalizer import extract_exact_anchors
from enterprise_rag.retrieval.models import EvidenceBundle


@dataclass(frozen=True, slots=True)
class EvidenceGrade:
    """中文：该类用于表示或实现“证据评级（EvidenceGrade）”的职责。

    English: Describe whether evidence is sufficient and why.
    """

    # 中文：变量 `sufficient` 用于保存“`sufficient`”相关数据；其精确定义与约束见下方英文说明。
    # English: Whether answering may proceed.
    sufficient: bool
    # 中文：变量 `coverage` 用于保存“`coverage`”相关数据；其精确定义与约束见下方英文说明。
    # English: Query-term coverage between zero and one.
    coverage: float
    # 中文：变量 `conflicting` 用于保存“`conflicting`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Whether the selected evidence contains a simple conflicting polarity signal.
    conflicting: bool
    # 中文：变量 `reason` 用于保存“原因”相关数据；其精确定义与约束见下方英文说明。
    # English: Safe explanation retained in agent state and traces.
    reason: str


class EvidenceGrader:
    """中文：该类用于表示或实现“证据评估器（EvidenceGrader）”的职责。

    English: Apply a deterministic first-version evidence sufficiency policy.
    """

    def __init__(self, minimum_coverage: float = 0.35, minimum_items: int = 1) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store minimum lexical coverage and evidence-count requirements.
        """

        # 中文：变量 `_minimum_coverage` 用于保存“`minimum``coverage`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Coverage threshold is intentionally configurable for evaluation.
        self._minimum_coverage = minimum_coverage
        # 中文：变量 `_minimum_items` 用于保存“`minimum``items`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: At least one evidence item is required in every configuration.
        self._minimum_items = max(1, minimum_items)

    def grade(self, query: str, evidence: EvidenceBundle) -> EvidenceGrade:
        """中文：该函数或方法负责“评级”相关处理。

        English: Return a reproducible grade without another model call.
        """

        if len(evidence.items) < self._minimum_items:
            return EvidenceGrade(False, 0.0, False, "No usable evidence was retrieved.")
        # 中文：变量 `query_terms` 用于保存“查询`terms`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Query terms use the same bilingual lexical tokenizer as BM25.
        query_terms = frozenset(
            term for term in lexical_tokens(query) if len(term) > 1 or ":" in term
        )
        # 中文：变量 `evidence_terms` 用于保存“证据`terms`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Evidence terms span every selected chunk.
        evidence_terms = frozenset(
            term
            for item in evidence.items
            for term in lexical_tokens(item.chunk.retrieval_text or item.chunk.text)
        )
        # 中文：条款、步骤、错误码等精确锚点必须真实出现在证据中，不能由普通词覆盖替代。
        # English: Exact clause, step, and code anchors must occur in evidence and cannot be
        # substituted by general lexical coverage.
        query_anchors = frozenset(extract_exact_anchors(query))
        evidence_anchors = frozenset(
            anchor
            for item in evidence.items
            for anchor in extract_exact_anchors(item.chunk.retrieval_text or item.chunk.text)
        )
        exact_anchors_covered = query_anchors <= evidence_anchors
        # 中文：变量 `coverage` 用于保存“`coverage`”相关数据；其精确定义与约束见下方英文说明。
        # English: Empty tokenized queries cannot be meaningfully covered.
        coverage = len(query_terms & evidence_terms) / len(query_terms) if query_terms else 0.0
        # 中文：变量 `joined` 用于保存“`joined`”相关数据；其精确定义与约束见下方英文说明。
        # English: Simple polarity detector flags direct positive/negative wording across
        #   evidence.
        joined = " ".join(item.chunk.text.lower() for item in evidence.items)
        positive_signal = any(token in joined for token in ("must ", "required", "应当", "必须"))
        negative_signal = any(
            token in joined for token in ("must not", "not required", "不得", "无需")
        )
        conflicting = positive_signal and negative_signal
        sufficient = (
            coverage >= self._minimum_coverage
            and exact_anchors_covered
            and not conflicting
        )
        reason = (
            "Evidence covers the query with no detected conflict."
            if sufficient
            else "Evidence coverage is insufficient or contains a conflict."
        )
        return EvidenceGrade(sufficient, coverage, conflicting, reason)
