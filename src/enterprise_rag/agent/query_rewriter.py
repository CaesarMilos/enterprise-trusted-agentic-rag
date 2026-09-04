"""中文：本模块负责实现“查询改写器”相关功能。

English: Rewrite a query from a concrete evidence gap while preventing retry loops.
"""

from __future__ import annotations

from dataclasses import dataclass

from enterprise_rag.agent.evidence_grader import EvidenceGrade
from enterprise_rag.agent.model_invocation import complete_with_timeout
from enterprise_rag.agent.prompts import REWRITE_SYSTEM_PROMPT
from enterprise_rag.domain.protocols.models import LLMProvider, ModelResponse
from enterprise_rag.indexing.bm25_index import lexical_tokens
from enterprise_rag.retrieval.identifier_normalizer import extract_exact_anchors


@dataclass(frozen=True, slots=True)
class RewriteDecision:
    """中文：记录是否采用改写、缺失 Need、保留锚点和语义漂移。

    English: Record rewrite adoption, missing needs, preserved anchors, and semantic drift.
    """

    should_rewrite: bool
    rewritten_query: str | None
    missing_need_ids: tuple[str, ...]
    preserved_anchors: tuple[str, ...]
    drift_score: float
    reason: str


class QueryRewriter:
    """中文：该类用于表示或实现“查询改写器（QueryRewriter）”的职责。

    English: Use a language model for one bounded search rewrite and reject duplicates.
    """

    def __init__(self, provider: LLMProvider, maximum_drift: float = 1.0) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store the configured provider-neutral language model.
        """

        # 中文：变量 `_provider` 用于保存“提供方”相关数据；其精确定义与约束见下方英文说明。
        # English: Provider differences remain encapsulated by the infrastructure adapter.
        self._provider = provider
        if not 0.0 <= maximum_drift <= 1.0:
            raise ValueError("maximum rewrite drift must be within [0, 1]")
        # 中文：漂移上限是程序门禁，不依赖 LLM 自我声明。
        # English: Drift is a programmatic gate, not an LLM self-assessment.
        self._maximum_drift = maximum_drift

    def rewrite(
        self,
        original_query: str,
        current_query: str,
        grade: EvidenceGrade,
        history: tuple[str, ...],
        timeout_seconds: float | None = None,
    ) -> tuple[str, ModelResponse]:
        """中文：该函数或方法负责“改写”相关处理。

        English: Return a non-empty novel search query and provider usage.
        """

        # 中文：变量 `user_prompt` 用于保存“用户提示词”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: User prompt contains only safe grade metadata, not raw hidden reasoning.
        user_prompt = (
            f"Original question: {original_query}\n"
            f"Current search query: {current_query}\n"
            f"Evidence gap: {grade.reason}\n"
            f"Coverage: {grade.coverage:.3f}\n"
            "Preserve every clause, chapter, step, error-code, and model identifier exactly.\n"
            "Return a better search query."
        )
        response = complete_with_timeout(
            self._provider,
            REWRITE_SYSTEM_PROMPT,
            user_prompt,
            {"operation": "query_rewrite"},
            timeout_seconds,
        )
        # 中文：变量 `rewritten` 用于保存“`rewritten`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Single-line normalization makes loop detection deterministic.
        rewritten = " ".join(response.text.split()).strip().strip('"')
        # 中文：模型若漏掉强锚点，程序会把规范锚点重新附加到改写查询。
        # English: Canonical anchors are reattached if the model omits strong identifiers.
        original_anchors = extract_exact_anchors(original_query)
        missing_anchors = tuple(
            anchor for anchor in original_anchors if anchor not in extract_exact_anchors(rewritten)
        )
        if missing_anchors:
            rewritten = f"{rewritten} {' '.join(missing_anchors)}".strip()
        # 中文：变量 `seen` 用于保存“`seen`”相关数据；其精确定义与约束见下方英文说明。
        # English: All previous forms are compared case-insensitively.
        seen = {original_query.casefold(), current_query.casefold()}
        seen.update(query.casefold() for query in history)
        if not rewritten or rewritten.casefold() in seen:
            raise ValueError("query rewriter returned an empty or duplicate query")
        drift = _semantic_drift(current_query, rewritten)
        if drift > self._maximum_drift:
            raise ValueError("query rewriter exceeded the semantic drift threshold")
        return rewritten, response

    def decide(
        self,
        original_query: str,
        current_query: str,
        grade: EvidenceGrade,
        history: tuple[str, ...],
        timeout_seconds: float | None = None,
    ) -> tuple[RewriteDecision, ModelResponse]:
        """中文：生成并验证一次可解释改写决策。

        English: Generate and validate one explainable rewrite decision.
        """

        rewritten, response = self.rewrite(
            original_query,
            current_query,
            grade,
            history,
            timeout_seconds,
        )
        anchors = extract_exact_anchors(original_query)
        return (
            RewriteDecision(
                should_rewrite=True,
                rewritten_query=rewritten,
                missing_need_ids=grade.missing_need_ids,
                preserved_anchors=tuple(
                    anchor for anchor in anchors if anchor in extract_exact_anchors(rewritten)
                ),
                drift_score=_semantic_drift(current_query, rewritten),
                reason="NEW_QUERY_PRESERVES_ANCHORS_AND_STAYS_WITHIN_DRIFT_BUDGET",
            ),
            response,
        )


def _semantic_drift(original: str, rewritten: str) -> float:
    """中文：用字符级稳定 Token Jaccard 距离作为保守的漂移门禁。

    English: Use stable token Jaccard distance as a conservative semantic-drift gate.
    """

    original_terms = set(lexical_tokens(original))
    rewritten_terms = set(lexical_tokens(rewritten))
    if not original_terms:
        return 1.0
    union = original_terms | rewritten_terms
    return 1.0 - len(original_terms & rewritten_terms) / len(union) if union else 0.0
