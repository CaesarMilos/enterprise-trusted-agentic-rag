"""中文：本模块负责实现“查询改写器”相关功能。

English: Rewrite a query from a concrete evidence gap while preventing retry loops.
"""

from __future__ import annotations

from enterprise_rag.agent.evidence_grader import EvidenceGrade
from enterprise_rag.agent.model_invocation import complete_with_timeout
from enterprise_rag.agent.prompts import REWRITE_SYSTEM_PROMPT
from enterprise_rag.domain.protocols.models import LLMProvider, ModelResponse
from enterprise_rag.retrieval.identifier_normalizer import extract_exact_anchors


class QueryRewriter:
    """中文：该类用于表示或实现“查询改写器（QueryRewriter）”的职责。

    English: Use a language model for one bounded search rewrite and reject duplicates.
    """

    def __init__(self, provider: LLMProvider) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store the configured provider-neutral language model.
        """

        # 中文：变量 `_provider` 用于保存“提供方”相关数据；其精确定义与约束见下方英文说明。
        # English: Provider differences remain encapsulated by the infrastructure adapter.
        self._provider = provider

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
        return rewritten, response
