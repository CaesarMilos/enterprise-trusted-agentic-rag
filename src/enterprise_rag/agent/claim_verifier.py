"""中文：验证最终答案断言是否被所引证据在语义上支撑。

English: Verify that final answer claims are semantically supported by cited evidence.
"""

from __future__ import annotations

from dataclasses import dataclass

from enterprise_rag.agent.proposition_extractor import semantic_signals
from enterprise_rag.indexing.bm25_index import lexical_tokens
from enterprise_rag.retrieval.identifier_normalizer import extract_exact_anchors
from enterprise_rag.retrieval.models import EvidenceItem


@dataclass(frozen=True, slots=True)
class ClaimSupport:
    """中文：保存一条答案断言的可审计支撑判定。

    English: Store an auditable support decision for one answer claim.
    """

    # 中文：`supported` 表示所有确定性约束均已通过。
    # English: `supported` is true only when every deterministic constraint passes.
    supported: bool
    # 中文：`reason_code` 是稳定的拒绝或通过原因。
    # English: `reason_code` is the stable pass or rejection reason.
    reason_code: str
    # 中文：`lexical_overlap` 保留词面支撑比例用于追踪。
    # English: `lexical_overlap` retains lexical support coverage for tracing.
    lexical_overlap: float


class ClaimVerifier:
    """中文：组合词面、锚点、实体、时间、模态和数值一致性约束。

    English: Combine lexical, anchor, entity, temporal, modality, and numeric consistency rules.
    """

    def __init__(self, minimum_lexical_overlap: float = 0.15) -> None:
        """中文：保存最低词面覆盖率，并校验其合法范围。

        English: Store and validate the minimum lexical-overlap threshold.
        """

        if not 0.0 <= minimum_lexical_overlap <= 1.0:
            raise ValueError("minimum lexical overlap must be within [0, 1]")
        self._minimum_lexical_overlap = minimum_lexical_overlap

    def verify(self, claim_text: str, cited_items: tuple[EvidenceItem, ...]) -> ClaimSupport:
        """中文：拒绝仅相似但缺失关键语义槽位的引文支撑。

        English: Reject citation support that is merely similar but lacks critical semantics.
        """

        evidence_text = "\n".join(item.chunk.search_text for item in cited_items)
        claim_terms = _meaningful_terms(claim_text)
        evidence_terms = _meaningful_terms(evidence_text)
        overlap = len(claim_terms & evidence_terms) / len(claim_terms) if claim_terms else 0.0
        claim_anchors = extract_exact_anchors(claim_text)
        evidence_anchors = extract_exact_anchors(evidence_text)
        if not claim_anchors <= evidence_anchors:
            return ClaimSupport(False, "CLAIM_ANCHOR_NOT_IN_EVIDENCE", overlap)

        claim_signals = semantic_signals(claim_text)
        evidence_signals = semantic_signals(evidence_text)
        if (
            claim_signals.temporal_roles
            and not claim_signals.temporal_roles <= evidence_signals.temporal_roles
        ):
            return ClaimSupport(False, "CLAIM_TIME_ROLE_NOT_IN_EVIDENCE", overlap)
        if claim_signals.modalities and not claim_signals.modalities <= evidence_signals.modalities:
            return ClaimSupport(False, "CLAIM_MODALITY_NOT_IN_EVIDENCE", overlap)
        if claim_signals.entities and not claim_signals.entities <= evidence_signals.entities:
            return ClaimSupport(False, "CLAIM_ENTITY_NOT_IN_EVIDENCE", overlap)
        if claim_signals.numbers and not claim_signals.numbers <= evidence_signals.numbers:
            return ClaimSupport(False, "CLAIM_NUMBER_NOT_IN_EVIDENCE", overlap)
        if overlap < self._minimum_lexical_overlap:
            return ClaimSupport(False, "LEXICAL_SUPPORT_TOO_LOW", overlap)
        return ClaimSupport(True, "CLAIM_SUPPORTED", overlap)


def _meaningful_terms(text: str) -> frozenset[str]:
    """中文：过滤无判别力单字，计算与现有 BM25 一致的词面集合。

    English: Filter uninformative characters and use the same lexical vocabulary as BM25.
    """

    return frozenset(term for term in lexical_tokens(text) if len(term) > 1 or ":" in term)
