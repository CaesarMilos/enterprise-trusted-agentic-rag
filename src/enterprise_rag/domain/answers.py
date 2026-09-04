"""中文：定义逐项回答、已验证 Claim、引用和缺失信息的 V5 协议。

English: Define the V5 protocol for answer items, verified claims, citations, and missing needs.
"""

from __future__ import annotations

from dataclasses import dataclass

from enterprise_rag.core.enums import (
    AnswerStatus,
    ClaimVerificationStatus,
    EvidenceStatus,
    RefusalReason,
)
from enterprise_rag.domain.locators import LocatorBundle


@dataclass(frozen=True, slots=True)
class VerifiedCitation:
    """中文：保存已通过快照、权限、版本和位置复核的引用。

    English: Store a citation verified against snapshot, authorization, version, and location.
    """

    id: str
    evidence_id: str
    chunk_id: str
    document_id: str
    document_version_id: str
    source_id: str
    snapshot_id: str
    title: str
    locator: LocatorBundle
    excerpt: str | None = None


@dataclass(frozen=True, slots=True)
class AnswerClaim:
    """中文：表示一条已绑定信息需要、证据和引用的答案结论。

    English: Represent an answer conclusion bound to needs, evidence, and citations.
    """

    id: str
    text: str
    need_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    citation_ids: tuple[str, ...]
    verification_status: ClaimVerificationStatus

    def __post_init__(self) -> None:
        """中文：要求 Claim 至少绑定一个信息需要和证据。

        English: Require every claim to bind at least one need and evidence item.
        """

        if not self.id or not self.text.strip():
            raise ValueError("answer claim requires identity and text")
        if not self.need_ids or not self.evidence_ids:
            raise ValueError("answer claim requires need and evidence bindings")


@dataclass(frozen=True, slots=True)
class AnswerItem:
    """中文：表示面向用户的一项回答及其已验证 Claim。

    English: Represent one user-facing answer item and its verified claims.
    """

    id: str
    need_ids: tuple[str, ...]
    text: str
    claim_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        """中文：拒绝没有信息需要或 Claim 的展示项。

        English: Reject display items without information needs or claims.
        """

        if not self.id or not self.text.strip() or not self.need_ids or not self.claim_ids:
            raise ValueError("answer item requires identity, text, needs, and claims")


@dataclass(frozen=True, slots=True)
class MissingInformation:
    """中文：说明未被证据完整支持的信息需要。

    English: Explain an information need that evidence did not fully support.
    """

    need_id: str
    description: str
    reason: EvidenceStatus


@dataclass(frozen=True, slots=True)
class ConflictDisclosure:
    """中文：向用户披露证据冲突而不自动裁决权威结论。

    English: Disclose an evidence conflict without automatically deciding authority.
    """

    need_id: str
    proposition_ids: tuple[str, ...]
    message: str


@dataclass(frozen=True, slots=True)
class VerifiedAnswer:
    """中文：保存经过证据、Claim、引用和当前授权复核的最终回答。

    English: Store a final answer verified for evidence, claims, citations, and current access.
    """

    schema_version: str
    status: AnswerStatus
    answer_text: str | None
    items: tuple[AnswerItem, ...]
    claims: tuple[AnswerClaim, ...]
    citations: tuple[VerifiedCitation, ...]
    missing_information: tuple[MissingInformation, ...]
    conflicts: tuple[ConflictDisclosure, ...]
    refusal_reason: RefusalReason | None
    trace_id: str
    snapshot_id: str
    index_version_id: str
    retrieval_rounds: int

    def __post_init__(self) -> None:
        """中文：在对象创建时执行完整的公开回答不变量校验。

        English: Enforce all public-answer invariants when the object is constructed.
        """

        validate_verified_answer(self)


def validate_verified_answer(answer: VerifiedAnswer) -> None:
    """中文：拒绝未验证 Claim、悬空引用和状态不一致的回答。

    English: Reject unverified claims, dangling citations, and inconsistent answer states.
    """

    if not answer.schema_version or not answer.trace_id or not answer.snapshot_id:
        raise ValueError("verified answer requires schema, trace, and snapshot identities")
    if not answer.index_version_id or answer.retrieval_rounds < 0:
        raise ValueError("verified answer requires index identity and non-negative rounds")
    claim_by_id = {claim.id: claim for claim in answer.claims}
    citation_by_id = {citation.id: citation for citation in answer.citations}
    item_ids = {item.id for item in answer.items}
    if len(claim_by_id) != len(answer.claims):
        raise ValueError("answer claim IDs must be unique")
    if len(citation_by_id) != len(answer.citations):
        raise ValueError("answer citation IDs must be unique")
    if len(item_ids) != len(answer.items):
        raise ValueError("answer item IDs must be unique")
    for item in answer.items:
        if any(claim_id not in claim_by_id for claim_id in item.claim_ids):
            raise ValueError("answer item references an unknown claim")
    referenced_citations: set[str] = set()
    for claim in answer.claims:
        if claim.verification_status is not ClaimVerificationStatus.VERIFIED:
            raise ValueError("public answers may contain verified claims only")
        if not claim.citation_ids:
            raise ValueError("verified claims require at least one citation")
        if any(citation_id not in citation_by_id for citation_id in claim.citation_ids):
            raise ValueError("answer claim references an unknown citation")
        referenced_citations.update(claim.citation_ids)
    if referenced_citations != set(citation_by_id):
        raise ValueError("verified answer contains dangling or unused citations")
    if any(citation.snapshot_id != answer.snapshot_id for citation in answer.citations):
        raise ValueError("all citations must belong to the answer snapshot")
    if answer.status is AnswerStatus.ANSWERED:
        if not answer.answer_text or not answer.items or not answer.claims:
            raise ValueError("answered result requires text, items, and claims")
        if answer.missing_information or answer.refusal_reason is not None:
            raise ValueError("answered result cannot contain missing information or refusal")
    elif answer.status is AnswerStatus.PARTIAL:
        if not answer.answer_text or not answer.items or not answer.missing_information:
            raise ValueError("partial result requires answer items and missing information")
        if answer.refusal_reason is not None:
            raise ValueError("partial result cannot carry a refusal reason")
    elif answer.status is AnswerStatus.REFUSED:
        if answer.answer_text or answer.items or answer.claims or answer.citations:
            raise ValueError("refused result cannot expose answer content or citations")
        if answer.refusal_reason is None:
            raise ValueError("refused result requires a refusal reason")
    elif answer.status is AnswerStatus.CONFLICTING:
        if not answer.conflicts:
            raise ValueError("conflicting result requires conflict disclosures")
        if answer.refusal_reason is not None:
            raise ValueError("conflicting result cannot carry a refusal reason")
