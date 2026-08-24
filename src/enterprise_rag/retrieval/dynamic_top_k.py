"""中文：本模块负责实现“动态TopK 值”相关功能。

English: Select an explainable evidence count from score gaps, diversity, and token budget.
"""

from __future__ import annotations

from collections.abc import Mapping

from enterprise_rag.domain.models import Chunk
from enterprise_rag.retrieval.models import RetrievalCandidate, TopKDecision


class DynamicTopK:
    """中文：该类用于表示或实现“动态TopK 值（DynamicTopK）”的职责。

    English: Choose between configured minimum and maximum evidence counts deterministically.
    """

    def __init__(
        self,
        min_k: int,
        default_k: int,
        max_k: int,
        token_budget: int,
        score_gap_ratio: float = 0.35,
    ) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store validated evidence-count and context-budget limits.
        """

        if not 1 <= min_k <= default_k <= max_k:
            raise ValueError("Top-K bounds must satisfy 1 <= min <= default <= max")
        # 中文：变量 `_min_k` 用于保存“`min``k`”相关数据；其精确定义与约束见下方英文说明。
        # English: Lower bound used when enough candidates fit.
        self._min_k = min_k
        # 中文：变量 `_default_k` 用于保存“默认`k`”相关数据；其精确定义与约束见下方英文说明。
        # English: Default used when score distribution has no clear break.
        self._default_k = default_k
        # 中文：变量 `_max_k` 用于保存“`max``k`”相关数据；其精确定义与约束见下方英文说明。
        # English: Hard evidence-count ceiling.
        self._max_k = max_k
        # 中文：变量 `_token_budget` 用于保存“词元预算”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Hard context token ceiling.
        self._token_budget = token_budget
        # 中文：变量 `_score_gap_ratio` 用于保存“`score``gap``ratio`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Relative consecutive score drop considered a meaningful boundary.
        self._score_gap_ratio = score_gap_ratio

    def select(
        self,
        candidates: tuple[RetrievalCandidate, ...],
        chunks: Mapping[str, Chunk],
    ) -> tuple[tuple[RetrievalCandidate, ...], TopKDecision]:
        """中文：该函数或方法负责“选择”相关处理。

        English: Return diverse candidates fitting both a dynamic count and token budget.
        """

        # 中文：变量 `available` 用于保存“`available`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Only candidates with available authorized chunks may enter evidence.
        available = tuple(candidate for candidate in candidates if candidate.chunk_id in chunks)
        if not available:
            return (), TopKDecision(0, "No authorized candidates were available.")
        # 中文：变量 `target` 用于保存“`target`”相关数据；其精确定义与约束见下方英文说明。
        # English: Initial target is bounded by the candidate count and configured default.
        target = min(self._default_k, len(available), self._max_k)
        # 中文：变量 `gap_reason` 用于保存“`gap`原因”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Score gaps after the minimum can shrink or expand the default selection.
        gap_reason = "Used configured default evidence count."
        upper_scan = min(len(available), self._max_k)
        for index in range(self._min_k - 1, upper_scan - 1):
            # 中文：变量 `current_score` 用于保存“当前`score`”相关数据；
            # 其精确定义与约束见下方英文说明。
            # English: Current and next scores are compared in the same post-fusion/rerank
            #   space.
            current_score = available[index].score
            next_score = available[index + 1].score
            # 中文：变量 `relative_drop` 用于保存“`relative``drop`”相关数据；
            # 其精确定义与约束见下方英文说明。
            # English: Denominator avoids division by zero for an all-zero score space.
            relative_drop = (current_score - next_score) / max(abs(current_score), 1e-12)
            if relative_drop >= self._score_gap_ratio:
                target = index + 1
                gap_reason = "Stopped at a meaningful relevance-score gap."
                break
        target = max(min(target, upper_scan), min(self._min_k, upper_scan))
        # 中文：变量 `selected` 用于保存“选中的”相关数据；其精确定义与约束见下方英文说明。
        # English: Selected items enforce document diversity and context budget in rank
        #   order.
        selected: list[RetrievalCandidate] = []
        # 中文：变量 `document_counts` 用于保存“文档`counts`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Per-document count prevents one document from monopolizing evidence.
        document_counts: dict[str, int] = {}
        # 中文：只有存在替代文档时才启用文档多样性上限。
        # English: Per-document diversity limits apply only when alternative documents exist.
        available_document_ids = {
            chunks[candidate.chunk_id].document_id for candidate in available[: self._max_k]
        }
        selected_families: set[str] = set()
        # 中文：变量 `used_tokens` 用于保存“`used`词元”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Running token sum applies the hard context ceiling.
        used_tokens = 0
        # 中文：变量 `dropped` 用于保存“`dropped`”相关数据；其精确定义与约束见下方英文说明。
        # English: Dropped identifiers explain deduplication and budget decisions.
        dropped: list[str] = []
        for candidate in available[: self._max_k]:
            chunk = chunks[candidate.chunk_id]
            family_id = chunk.parent_chunk_id or chunk.id
            if family_id in selected_families:
                dropped.append(candidate.chunk_id)
                continue
            # 中文：变量 `document_limit` 用于保存“文档`limit`”相关数据；
            # 其精确定义与约束见下方英文说明。
            # English: At most half the target may come from one document when
            #   alternatives exist.
            document_limit = (
                max(1, (target + 1) // 2)
                if len(available_document_ids) > 1
                else target
            )
            if document_counts.get(chunk.document_id, 0) >= document_limit:
                dropped.append(candidate.chunk_id)
                continue
            if used_tokens + chunk.token_count > self._token_budget:
                dropped.append(candidate.chunk_id)
                continue
            selected.append(candidate)
            selected_families.add(family_id)
            document_counts[chunk.document_id] = document_counts.get(chunk.document_id, 0) + 1
            used_tokens += chunk.token_count
            if len(selected) >= target:
                break
        # 中文：变量 `reason` 用于保存“原因”相关数据；其精确定义与约束见下方英文说明。
        # English: Token budget may produce fewer than min_k and is never exceeded to
        #   compensate.
        reason = (
            f"{gap_reason} Selected {len(selected)} item(s) within "
            f"{used_tokens}/{self._token_budget} estimated tokens."
        )
        return (
            tuple(selected),
            TopKDecision(
                selected_k=len(selected),
                reason=reason,
                dropped_chunk_ids=tuple(dropped),
            ),
        )
