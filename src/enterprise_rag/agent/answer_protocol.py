"""中文：把已验证文本转换为 Claim—Evidence 可追溯的 V5 回答协议。

English: Convert verified text into the V5 claim-to-evidence traceable answer protocol.
"""

from __future__ import annotations

import re

from enterprise_rag.agent.evidence_grader import EvidenceGrade
from enterprise_rag.core.enums import (
    AnswerStatus,
    ClaimVerificationStatus,
    EvidenceStatus,
)
from enterprise_rag.domain.answers import (
    AnswerClaim,
    AnswerItem,
    MissingInformation,
    VerifiedAnswer,
    VerifiedCitation,
)
from enterprise_rag.domain.locators import (
    DisplayLocator,
    LocatorBundle,
    LocatorMappingQuality,
    NormalizedRange,
    OriginalLocator,
)
from enterprise_rag.domain.models import Chunk, Citation, RetrievalScope
from enterprise_rag.domain.questions import QuestionPlan
from enterprise_rag.retrieval.models import EvidenceBundle

# 中文：只接受 CitationVerifier 已验证的方括号标签，并按回答句子建立 Claim。
# English: Accept only bracket labels already checked by CitationVerifier and build claims per
# answer sentence.
_CITATION_PATTERN = re.compile(r"\[C(\d+)]")
_CLAIM_PATTERN = re.compile(r"(?<=[。！？!?])\s*|(?<=[.])\s+")


def build_verified_answer(
    *,
    answer_text: str,
    citations: tuple[Citation, ...],
    evidence: EvidenceBundle,
    plan: QuestionPlan,
    grade: EvidenceGrade,
    scope: RetrievalScope,
    trace_id: str,
    retrieval_rounds: int,
    status: AnswerStatus,
) -> VerifiedAnswer:
    """中文：绑定句子、Need、Evidence 和 Locator，并由领域对象执行最终不变量校验。

    English: Bind sentences, needs, evidence, and locators, then let the domain object enforce
    final invariants.
    """

    if status not in {AnswerStatus.ANSWERED, AnswerStatus.PARTIAL}:
        raise ValueError("answer protocol builder accepts answered or partial status only")
    # 中文：`snapshot_id` 在服务路径中来自持久快照；兼容直接编排器测试时使用 Trace 范围。
    # English: `snapshot_id` comes from a durable service snapshot; direct orchestrator tests
    # use a trace-scoped compatibility identity.
    snapshot_id = scope.snapshot_id or f"trace-snapshot:{trace_id}"
    evidence_by_label = {item.citation_id: item for item in evidence.items}
    citation_by_label = {citation.citation_id: citation for citation in citations}
    grade_by_need = {item.need_id: item for item in grade.need_grades}
    need_by_id = {need.id: need for need in plan.needs}
    supported_need_ids = tuple(
        need.id
        for need in plan.needs
        if grade_by_need.get(need.id) is not None
        and grade_by_need[need.id].status is EvidenceStatus.SUPPORTED
    )

    claims: list[AnswerClaim] = []
    items: list[AnswerItem] = []
    used_labels: list[str] = []
    for raw_claim in _CLAIM_PATTERN.split(answer_text):
        claim_text = _CITATION_PATTERN.sub("", raw_claim).strip()
        labels = tuple(
            dict.fromkeys(f"C{number}" for number in _CITATION_PATTERN.findall(raw_claim))
        )
        if not claim_text:
            continue
        if not labels:
            raise ValueError("verified protocol cannot bind an uncited claim")
        claim_need_ids = tuple(
            need_id
            for need_id in supported_need_ids
            if any(label in grade_by_need[need_id].supporting_evidence_ids for label in labels)
        )
        # 中文：单 Need 问题允许把已验证引用确定性绑定到唯一 Need；多 Need 时禁止猜测。
        # English: A single supported-need question permits deterministic fallback binding;
        # multi-need answers never guess an ambiguous association.
        if not claim_need_ids and len(supported_need_ids) == 1:
            claim_need_ids = supported_need_ids
        if not claim_need_ids:
            raise ValueError("a verified claim cannot be mapped to a supported information need")
        if any(
            label not in citation_by_label or label not in evidence_by_label for label in labels
        ):
            raise ValueError("verified claim references an unavailable citation")
        claim_id = f"claim-{len(claims) + 1}"
        claims.append(
            AnswerClaim(
                id=claim_id,
                text=claim_text,
                need_ids=claim_need_ids,
                evidence_ids=labels,
                citation_ids=labels,
                verification_status=ClaimVerificationStatus.VERIFIED,
            )
        )
        items.append(
            AnswerItem(
                id=f"item-{len(items) + 1}",
                need_ids=claim_need_ids,
                text=claim_text,
                claim_ids=(claim_id,),
            )
        )
        for label in labels:
            if label not in used_labels:
                used_labels.append(label)

    verified_citations = tuple(
        _verified_citation(
            label,
            citation_by_label[label],
            evidence_by_label[label].chunk,
            snapshot_id,
        )
        for label in used_labels
    )
    missing = tuple(
        MissingInformation(
            need_id=need_id,
            description=need_by_id[need_id].description,
            reason=grade_by_need[need_id].status,
        )
        for need_id in grade.missing_need_ids
        if need_id in need_by_id and need_id in grade_by_need
    )
    return VerifiedAnswer(
        schema_version="verified-answer-v1",
        status=status,
        answer_text=answer_text,
        items=tuple(items),
        claims=tuple(claims),
        citations=verified_citations,
        missing_information=missing if status is AnswerStatus.PARTIAL else (),
        conflicts=(),
        refusal_reason=None,
        trace_id=trace_id,
        snapshot_id=snapshot_id,
        index_version_id=evidence.index_version_id,
        retrieval_rounds=retrieval_rounds,
    )


def _verified_citation(
    label: str,
    citation: Citation,
    chunk: Chunk,
    snapshot_id: str,
) -> VerifiedCitation:
    """中文：把公开引用升级为携带三层坐标和快照身份的引用。

    English: Upgrade a public citation with three-layer location and snapshot identity.
    """

    locator = chunk.locator or _fallback_locator(chunk, citation)
    return VerifiedCitation(
        id=label,
        evidence_id=label,
        chunk_id=citation.chunk_id,
        document_id=citation.document_id,
        document_version_id=citation.document_version_id,
        source_id=citation.source_id,
        snapshot_id=snapshot_id,
        title=citation.title,
        locator=locator,
        excerpt=citation.excerpt,
    )


def _fallback_locator(chunk: Chunk, citation: Citation) -> LocatorBundle:
    """中文：为 V4 历史 Chunk 构造保守 Locator，绝不伪装为精确原文映射。

    English: Construct a conservative locator for V4 chunks without pretending exact source
    mapping.
    """

    end = chunk.source_end_offset
    if end <= chunk.source_start_offset:
        end = chunk.source_start_offset + max(1, len(chunk.text))
    return LocatorBundle(
        original=OriginalLocator(
            page_start=citation.page_start,
            page_end=citation.page_end,
            block_ids=(chunk.id,),
        ),
        normalized=NormalizedRange(start=chunk.source_start_offset, end=end),
        display=DisplayLocator(
            title=citation.title,
            heading_path=chunk.heading_path,
            structural_anchor=chunk.section_number,
            page_start=citation.page_start,
            page_end=citation.page_end,
        ),
        mapping_quality=(
            LocatorMappingQuality.PAGE_ONLY
            if citation.page_start is not None
            else LocatorMappingQuality.APPROXIMATE
        ),
    )
