"""中文：本模块负责实现“动态TopK 值”相关功能。

English: Select an explainable evidence count from score gaps, diversity, and token budget.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

from enterprise_rag.agent.proposition_extractor import required_temporal_roles, semantic_signals
from enterprise_rag.domain.models import Chunk
from enterprise_rag.domain.questions import InformationNeed, QuestionPlan
from enterprise_rag.indexing.bm25_index import lexical_tokens
from enterprise_rag.retrieval.identifier_normalizer import extract_exact_anchors
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
        max_document_share: float = 0.6,
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
        if not 0.0 < max_document_share <= 1.0:
            raise ValueError("max_document_share must be within (0, 1]")
        # 中文：单文档证据占比防止长文档垄断最终上下文。
        # English: Per-document share prevents one long document monopolizing context.
        self._max_document_share = max_document_share

    def select(
        self,
        candidates: tuple[RetrievalCandidate, ...],
        chunks: Mapping[str, Chunk],
        plan: QuestionPlan | None = None,
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
        # English: Target expands for independent required needs and an explicit answer
        # cardinality, but never directly for raw anchor count.
        required_needs = (
            tuple(need for need in plan.needs if need.necessity.value == "required")
            if plan is not None
            else ()
        )
        requested_count = (
            plan.response_contract.requested_item_count
            if plan is not None and plan.response_contract.requested_item_count is not None
            else 0
        )
        target = min(
            max(self._default_k, len(required_needs), requested_count),
            len(available),
            self._max_k,
        )
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
        # 中文：分数断层可以压缩普通查询，但不得压缩到明示 Need/项数基数以下。
        # English: Score gaps may shrink ordinary queries but never below explicit need/cardinality
        # requirements.
        semantic_floor = min(
            max(self._min_k, len(required_needs), requested_count),
            upper_scan,
        )
        target = max(min(target, upper_scan), semantic_floor)
        # 中文：每个 required Need 先获得一个最佳候选配额，剩余名额再按全局排名填充。
        # English: Reserve the best candidate per required need, then fill remaining slots by
        # global rank.
        reserved_ids, candidate_need_ids = _reserve_need_candidates(
            required_needs,
            available,
            chunks,
            plan,
        )
        by_id = {candidate.chunk_id: candidate for candidate in available}
        selection_order = tuple(by_id[item] for item in reserved_ids) + tuple(
            candidate for candidate in available if candidate.chunk_id not in reserved_ids
        )
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
        selected_need_ids: set[str] = set()
        for candidate in selection_order[: self._max_k]:
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
                max(1, math.ceil(target * self._max_document_share))
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
            selected_need_ids.update(candidate_need_ids.get(candidate.chunk_id, ()))
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
                covered_need_ids=tuple(
                    need.id for need in required_needs if need.id in selected_need_ids
                ),
                uncovered_need_ids=tuple(
                    need.id for need in required_needs if need.id not in selected_need_ids
                ),
            ),
        )


def _reserve_need_candidates(
    needs: tuple[InformationNeed, ...],
    candidates: tuple[RetrievalCandidate, ...],
    chunks: Mapping[str, Chunk],
    plan: QuestionPlan | None,
) -> tuple[tuple[str, ...], dict[str, tuple[str, ...]]]:
    """中文：为每个独立 Need 保留一个最佳候选，同一 Chunk 可同时覆盖多个 Need。

    English: Reserve one best candidate per independent need while allowing one chunk to cover
    multiple needs.
    """

    if not needs:
        return (), {}
    anchors = {anchor.id: anchor.normalized_value for anchor in plan.anchors} if plan else {}
    candidate_need_ids: dict[str, tuple[str, ...]] = {}
    reserved: list[str] = []
    for need in needs:
        query_terms = _selection_terms(need.retrieval_query)
        # 中文：每个 Need 的关键时间角色构成候选资格，而不仅是排序加分。
        # English: Critical temporal roles qualify a candidate instead of merely boosting it.
        required_time_roles = required_temporal_roles(need.retrieval_query)
        required_anchors = {
            anchors[anchor_id] for anchor_id in need.anchor_ids if anchor_id in anchors
        }
        best: tuple[float, str] | None = None
        for rank, candidate in enumerate(candidates):
            chunk = chunks.get(candidate.chunk_id)
            if chunk is None:
                continue
            chunk_terms = _selection_terms(chunk.search_text)
            lexical = len(query_terms & chunk_terms) / len(query_terms) if query_terms else 0.0
            chunk_anchors = set(extract_exact_anchors(chunk.search_text))
            if required_anchors and not required_anchors <= chunk_anchors:
                continue
            if (
                required_time_roles
                and not required_time_roles <= semantic_signals(chunk.search_text).temporal_roles
            ):
                continue
            if lexical <= 0.0 and not required_anchors:
                continue
            # 中文：词汇覆盖优先，原始排名用作稳定平局因子。
            # English: Lexical coverage leads; original rank is a deterministic tie-breaker.
            score = lexical + 1.0 / (1000.0 + rank)
            if best is None or score > best[0]:
                best = (score, candidate.chunk_id)
        if best is None:
            continue
        chunk_id = best[1]
        if chunk_id not in reserved:
            reserved.append(chunk_id)
        current = candidate_need_ids.get(chunk_id, ())
        candidate_need_ids[chunk_id] = (*current, need.id)
    return tuple(reserved), candidate_need_ids


def _selection_terms(text: str) -> frozenset[str]:
    """中文：生成 Need 配额匹配用的稳定词项集。

    English: Build stable terms for need-quota matching.
    """

    return frozenset(term for term in lexical_tokens(text) if len(term) > 1 or ":" in term)
