"""中文：本模块负责实现“引用验证器”相关功能。

English: Verify citation existence, authorization, versions, positions, and lexical claim
support.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from enterprise_rag.agent.claim_verifier import ClaimVerifier
from enterprise_rag.domain.models import Citation, RetrievalScope
from enterprise_rag.indexing.bm25_index import lexical_tokens
from enterprise_rag.retrieval.models import EvidenceBundle, EvidenceItem

# 中文：变量 `_CITATION_PATTERN` 用于保存“引用`pattern`”相关数据；
# 其精确定义与约束见下方英文说明。
# English: Citation labels are the only accepted reference syntax in generated answers.
_CITATION_PATTERN = re.compile(r"\[C(\d+)]")
# 中文：变量 `_CLAIM_PATTERN` 用于保存“`claim``pattern`”相关数据；
# 其精确定义与约束见下方英文说明。
# English: Sentence split supports Chinese and Latin answer punctuation.
_CLAIM_PATTERN = re.compile(r"(?<=[。！？!?])\s*|(?<=[.])\s+")


@dataclass(frozen=True, slots=True)
class CitationVerification:
    """中文：该类用于表示或实现“引用验证（CitationVerification）”的职责。

    English: Describe citation validation outcome and public citation objects.
    """

    # 中文：变量 `valid` 用于保存“`valid`”相关数据；其精确定义与约束见下方英文说明。
    # English: Whether every factual claim and referenced item passed validation.
    valid: bool
    # 中文：变量 `citations` 用于保存“引用”相关数据；其精确定义与约束见下方英文说明。
    # English: Safe verified citations in first-use order.
    citations: tuple[Citation, ...]
    # 中文：变量 `reason` 用于保存“原因”相关数据；其精确定义与约束见下方英文说明。
    # English: Short safe failure or success explanation.
    reason: str


class CitationVerifier:
    """中文：该类用于表示或实现“引用验证器（CitationVerifier）”的职责。

    English: Enforce deterministic citation and basic claim-support rules.
    """

    def __init__(
        self,
        minimum_claim_overlap: float = 0.15,
        current_access_validator: Callable[[EvidenceItem, RetrievalScope], bool] | None = None,
    ) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store the minimum lexical overlap between a claim and cited evidence.
        """

        # 中文：变量 `_minimum_claim_overlap`
        #   用于保存“`minimum``claim``overlap`”相关数据；其精确定义与约束见下方英文说明。
        # English: Threshold is intentionally configurable for evaluation calibration.
        self._minimum_claim_overlap = minimum_claim_overlap
        # 中文：最终支撑判定升级为词面与关键语义槽位的联合校验。
        # English: Final support now combines lexical overlap with critical semantic slots.
        self._claim_verifier = ClaimVerifier(minimum_claim_overlap)
        # 中文：可选回调在回答返回前重查删除和 Source 撤权；
        # 普通索引切换仍允许固定快照完成。
        # English: The optional callback rechecks deletion and source revocation before return;
        # ordinary index switches may still complete their pinned snapshot.
        self._current_access_validator = current_access_validator

    def verify(
        self,
        answer: str,
        evidence: EvidenceBundle,
        scope: RetrievalScope,
    ) -> CitationVerification:
        """中文：该函数或方法负责“验证”相关处理。

        English: Return verified citation objects or one explicit failure reason.
        """

        if evidence.index_version_id != scope.index_version_id:
            return CitationVerification(False, (), "Evidence and scope index versions differ.")
        # 中文：变量 `by_label` 用于保存“`by`标签”相关数据；其精确定义与约束见下方英文说明。
        # English: Evidence map accepts only labels actually present in the final bundle.
        by_label = {item.citation_id: item for item in evidence.items}
        # 中文：变量 `ordered_labels` 用于保存“`ordered`标签”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Ordered labels are deduplicated while preserving first appearance.
        ordered_labels: list[str] = []
        for number in _CITATION_PATTERN.findall(answer):
            label = f"C{number}"
            if label not in ordered_labels:
                ordered_labels.append(label)
        if not ordered_labels:
            return CitationVerification(False, (), "The answer contains no citations.")
        if any(label not in by_label for label in ordered_labels):
            return CitationVerification(False, (), "The answer references unknown evidence.")
        # 中文：每个引用标签累积其实际支撑的回答词项，用于生成局部证据摘录。
        # English: Each label accumulates supported claim terms for a local citation excerpt.
        support_terms_by_label: dict[str, set[str]] = {}
        # 中文：本步骤涉及答案、关键词检索、证据，具体约束见下方英文说明。
        # English: Every answer sentence containing lexical content must cite one or more
        #   evidence items.
        for raw_claim in _CLAIM_PATTERN.split(answer):
            # 中文：变量 `labels` 用于保存“标签”相关数据；其精确定义与约束见下方英文说明。
            # English: Citation markers are removed before lexical-support comparison.
            labels = [f"C{number}" for number in _CITATION_PATTERN.findall(raw_claim)]
            claim_text = _CITATION_PATTERN.sub("", raw_claim).strip()
            claim_terms = frozenset(
                term for term in lexical_tokens(claim_text) if len(term) > 1 or ":" in term
            )
            if not claim_terms:
                continue
            if not labels:
                return CitationVerification(False, (), "A factual claim is missing a citation.")
            # 中文：变量 `cited_items` 用于保存“`cited``items`”相关数据；
            # 其精确定义与约束见下方英文说明。
            # English: Cited item ACL and version identity are revalidated at the final
            #   boundary.
            cited_items = tuple(by_label[label] for label in labels if label in by_label)
            if len(cited_items) != len(labels):
                return CitationVerification(False, (), "A claim references unknown evidence.")
            if not all(_authorized(item, scope) for item in cited_items):
                return CitationVerification(False, (), "A citation is outside the retrieval scope.")
            if self._current_access_validator is not None and not all(
                self._current_access_validator(item, scope) for item in cited_items
            ):
                return CitationVerification(
                    False,
                    (),
                    "A citation was revoked or deleted while the answer was running.",
                )
            # 中文：词面相似度不能替代实体、时间、模态、数字和锚点一致性。
            # English: Lexical similarity cannot substitute for entity, time, modality,
            # numeric, and exact-anchor consistency.
            claim_support = self._claim_verifier.verify(claim_text, cited_items)
            if not claim_support.supported:
                return CitationVerification(
                    False,
                    (),
                    f"A citation does not support its claim ({claim_support.reason_code}).",
                )
            for label in labels:
                support_terms_by_label.setdefault(label, set()).update(claim_terms)
        # 中文：变量 `citations` 用于保存“引用”相关数据；其精确定义与约束见下方英文说明。
        # English: Public citations are created only after the full answer passes.
        citations = tuple(
            _to_citation(by_label[label], support_terms_by_label.get(label, set()))
            for label in ordered_labels
        )
        return CitationVerification(True, citations, "All citations passed deterministic checks.")


def _authorized(item: EvidenceItem, scope: RetrievalScope) -> bool:
    """中文：该内部函数负责“已授权”相关处理。

    English: Return whether an evidence item remains inside the final retrieval scope.
    """

    chunk = item.chunk
    return scope.allows(
        chunk.tenant_id,
        chunk.source_id,
        chunk.document_id,
    ) and scope.allows_version(chunk.document_version_id)


def _to_citation(item: EvidenceItem, support_terms: set[str]) -> Citation:
    """中文：该内部函数负责“到引用”相关处理。

    English: Convert a verified evidence item into a public citation object.
    """

    # 中文：变量 `title` 用于保存“标题”相关数据；其精确定义与约束见下方英文说明。
    # English: Innermost heading is the best available local title.
    title = item.chunk.heading_path[-1] if item.chunk.heading_path else item.chunk.document_id
    # 中文：变量 `excerpt` 用于保存“`excerpt`”相关数据；其精确定义与约束见下方英文说明。
    # English: Short excerpt aids user inspection without duplicating the entire chunk.
    excerpt = _support_excerpt(item.chunk.text, support_terms)
    return Citation(
        citation_id=item.citation_id,
        chunk_id=item.chunk.id,
        document_id=item.chunk.document_id,
        document_version_id=item.chunk.document_version_id,
        source_id=item.chunk.source_id,
        title=title,
        page_start=item.chunk.page_start,
        page_end=item.chunk.page_end,
        excerpt=excerpt,
    )


def _support_excerpt(text: str, support_terms: set[str], limit: int = 280) -> str:
    """中文：返回围绕最佳词项重叠位置的局部摘录，而不是固定截取 Chunk 开头。

    English: Return a local excerpt around the best term-overlap position instead of always
    taking the chunk prefix.
    """

    if len(text) <= limit:
        return text.strip()
    candidate_starts = {0}
    lowered = text.lower()
    for term in support_terms:
        position = lowered.find(term.lower())
        if position >= 0:
            candidate_starts.add(max(0, position - limit // 3))
    best_start = max(
        candidate_starts,
        key=lambda start: len(set(lexical_tokens(text[start : start + limit])) & support_terms),
    )
    excerpt = text[best_start : best_start + limit].strip()
    prefix = "…" if best_start > 0 else ""
    suffix = "…" if best_start + limit < len(text) else ""
    return f"{prefix}{excerpt}{suffix}"
