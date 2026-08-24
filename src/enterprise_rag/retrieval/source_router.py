"""中文：本模块负责实现“资料源路由器”相关功能。

English: Automatically route a normalized query across already-authorized source profiles.
"""

from __future__ import annotations

from enterprise_rag.indexing.bm25_index import lexical_tokens
from enterprise_rag.retrieval.models import RetrievalQuery, RoutingResult


class SourceRouter:
    """中文：该类用于表示或实现“资料源路由器（SourceRouter）”的职责。

    English: Select one, several, or all authorized sources using deterministic profile overlap.
    """

    def __init__(self, relative_threshold: float = 0.55, max_sources: int = 4) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store routing cutoffs controlling multi-source breadth.
        """

        # 中文：变量 `_relative_threshold` 用于保存“`relative``threshold`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Relative threshold includes sources close to the best lexical profile
        #   match.
        self._relative_threshold = relative_threshold
        # 中文：变量 `_max_sources` 用于保存“`max`资料源”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Maximum prevents broad catalogs from expanding retrieval cost without
        #   bound.
        self._max_sources = max_sources

    def route(
        self,
        query: RetrievalQuery,
        profiles: tuple[dict[str, object], ...],
    ) -> RoutingResult:
        """中文：该函数或方法负责“路由”相关处理。

        English: Return a deterministic source subset contained in the authorized scope.
        """

        if not profiles:
            return RoutingResult((), "authorized_global", "No authorized source profiles exist.")
        # 中文：变量 `query_terms` 用于保存“查询`terms`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Query terms use the same bilingual tokenizer as lexical retrieval.
        query_terms = frozenset(lexical_tokens(query.normalized_text))
        query_terms = frozenset(
            term for term in query_terms if len(term) > 1 or ":" in term
        )
        # 中文：变量 `scores` 用于保存“`scores`”相关数据；其精确定义与约束见下方英文说明。
        # English: Score combines name, description, and derived profile term overlap.
        scores: dict[str, float] = {}
        for profile in profiles:
            # 中文：变量 `source_id` 用于保存“资料源标识符”相关数据；
            # 其精确定义与约束见下方英文说明。
            # English: Source ID originates from the ACL-filtered immutable catalog.
            source_id = str(profile["source_id"])
            # 中文：变量 `name_terms` 用于保存“`name``terms`”相关数据；
            # 其精确定义与约束见下方英文说明。
            # English: Name receives a small boost because it is an intentional
            #   administrator label.
            name_terms = frozenset(lexical_tokens(str(profile.get("name", ""))))
            description_terms = frozenset(lexical_tokens(str(profile.get("description", ""))))
            raw_profile_terms = profile.get("profile_terms", ())
            profile_terms = (
                frozenset(str(term) for term in raw_profile_terms)
                if isinstance(raw_profile_terms, (list, tuple, set, frozenset))
                else frozenset()
            )
            score = (
                2.0 * len(query_terms & name_terms)
                + 1.5 * len(query_terms & description_terms)
                + 1.0 * len(query_terms & profile_terms)
            )
            scores[source_id] = score
        # 中文：变量 `ranked` 用于保存“`ranked`”相关数据；其精确定义与约束见下方英文说明。
        # English: Stable order uses score descending and source ID ascending.
        ranked = sorted(scores, key=lambda source_id: (-scores[source_id], source_id))
        # 中文：变量 `best_score` 用于保存“`best``score`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Zero overlap uses the complete authorized scope instead of guessing a
        #   source.
        best_score = scores[ranked[0]]
        # 中文：低分、过多并列或领先优势不足时搜索全部授权资料源，避免提前误排除。
        # English: Weak scores, broad ties, or a narrow lead fall back to every authorized source.
        tied_best = tuple(source_id for source_id in ranked if scores[source_id] == best_score)
        second_score = scores[ranked[1]] if len(ranked) > 1 else 0.0
        weak_lead = len(ranked) > 1 and best_score < max(2.0, second_score * 1.15)
        if best_score <= 1.5 or len(tied_best) > self._max_sources or weak_lead:
            return RoutingResult(
                source_ids=tuple(ranked),
                mode="authorized_global",
                reason=(
                    "Source routing signal was weak or ambiguous; searched all authorized "
                    "sources."
                ),
                scores=scores,
            )
        # 中文：变量 `selected` 用于保存“选中的”相关数据；其精确定义与约束见下方英文说明。
        # English: Relative threshold retains plausible sources for cross-document
        #   questions.
        plausible = tuple(
            source_id
            for source_id in ranked
            if scores[source_id] >= best_score * self._relative_threshold
        )
        if len(plausible) > self._max_sources:
            return RoutingResult(
                source_ids=tuple(ranked),
                mode="authorized_global",
                reason=(
                    "Too many sources were similarly plausible; searched all authorized "
                    "sources."
                ),
                scores=scores,
            )
        selected = plausible
        return RoutingResult(
            source_ids=selected,
            mode="single_source" if len(selected) == 1 else "multi_source",
            reason="Selected sources by authorized profile overlap.",
            scores=scores,
        )
