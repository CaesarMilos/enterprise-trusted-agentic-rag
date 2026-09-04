"""中文：定义按信息需要评分的证据、命题和冲突关系契约。

English: Define need-level evidence, proposition, and conflict relationship contracts.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from enterprise_rag.core.enums import (
    ClaimModality,
    EvidenceCoverageDecision,
    EvidenceStatus,
    NeedNecessity,
    PropositionRelationship,
)
from enterprise_rag.domain.questions import QuestionPlan


@dataclass(frozen=True, slots=True)
class EvidenceProposition:
    """中文：表示只能追溯到已有证据原文范围的结构化命题。

    English: Represent a structured proposition traceable to an existing evidence span.
    """

    id: str
    subject: str | None
    predicate: str | None
    object: str | None
    modality: ClaimModality
    conditions: tuple[str, ...]
    exceptions: tuple[str, ...]
    temporal_scope: str | None
    authority_scope: str | None
    source_chunk_id: str
    source_span_start: int
    source_span_end: int
    extraction_method: str
    extraction_confidence: float | None = None

    def __post_init__(self) -> None:
        """中文：校验证据范围并要求模型抽取记录真实置信度。

        English: Validate evidence spans and require confidence for model extraction.
        """

        if not self.id or not self.source_chunk_id or not self.extraction_method:
            raise ValueError("evidence proposition requires identity, source, and method")
        if self.source_span_start < 0 or self.source_span_end <= self.source_span_start:
            raise ValueError("evidence proposition span must satisfy 0 <= start < end")
        if self.extraction_confidence is not None:
            if not 0.0 <= self.extraction_confidence <= 1.0:
                raise ValueError("proposition extraction confidence must be within [0, 1]")
        if self.extraction_method.startswith("llm") and self.extraction_confidence is None:
            raise ValueError("LLM proposition extraction requires confidence")


@dataclass(frozen=True, slots=True)
class EvidenceConflict:
    """中文：记录两条命题之间经过约束判断的关系。

    English: Record a constrained relationship between two evidence propositions.
    """

    left_proposition_id: str
    right_proposition_id: str
    relationship: PropositionRelationship
    reason_code: str
    judge_method: str

    def __post_init__(self) -> None:
        """中文：拒绝自冲突和缺少稳定原因的关系记录。

        English: Reject self-conflicts and relationships without stable reason metadata.
        """

        if self.left_proposition_id == self.right_proposition_id:
            raise ValueError("a proposition cannot conflict with itself")
        if not self.reason_code or not self.judge_method:
            raise ValueError("evidence relationship requires reason code and judge method")


@dataclass(frozen=True, slots=True)
class NeedEvidenceGrade:
    """中文：描述一个信息需要的证据覆盖、缺口和冲突。

    English: Describe evidence coverage, gaps, and conflicts for one information need.
    """

    need_id: str
    status: EvidenceStatus
    supporting_evidence_ids: tuple[str, ...] = ()
    partial_evidence_ids: tuple[str, ...] = ()
    conflicts: tuple[EvidenceConflict, ...] = ()
    missing_requirements: tuple[str, ...] = ()
    coverage_score: float = 0.0
    grading_method: str = "deterministic"

    def __post_init__(self) -> None:
        """中文：根据离散状态验证证据、缺口和冲突的必要字段。

        English: Validate required evidence, gaps, and conflicts for the discrete status.
        """

        if not self.need_id or not self.grading_method:
            raise ValueError("need evidence grade requires identity and method")
        if not 0.0 <= self.coverage_score <= 1.0:
            raise ValueError("evidence coverage score must be within [0, 1]")
        if self.status is EvidenceStatus.SUPPORTED:
            if not self.supporting_evidence_ids or self.missing_requirements:
                raise ValueError("supported need requires evidence and no missing requirements")
            if any(
                conflict.relationship is PropositionRelationship.CONFLICT
                for conflict in self.conflicts
            ):
                raise ValueError("supported need cannot contain a true conflict")
        elif self.status is EvidenceStatus.PARTIALLY_SUPPORTED:
            if not (self.supporting_evidence_ids or self.partial_evidence_ids):
                raise ValueError("partially supported need requires some evidence")
            if not self.missing_requirements:
                raise ValueError("partially supported need requires missing requirements")
        elif self.status is EvidenceStatus.UNSUPPORTED:
            if self.supporting_evidence_ids or not self.missing_requirements:
                raise ValueError("unsupported need must have no supporting evidence and a gap")
        elif self.status is EvidenceStatus.CONFLICTING:
            if not any(
                conflict.relationship is PropositionRelationship.CONFLICT
                for conflict in self.conflicts
            ):
                raise ValueError("conflicting need requires at least one true conflict")


@dataclass(frozen=True, slots=True)
class EvidenceCoverage:
    """中文：保存所有信息需要评分及 required-only 聚合决策。

    English: Store all need grades and the required-only aggregate decision.
    """

    grades: tuple[NeedEvidenceGrade, ...]
    decision: EvidenceCoverageDecision
    supported_required_need_ids: tuple[str, ...]
    unresolved_required_need_ids: tuple[str, ...]
    optional_need_ids: tuple[str, ...]


def build_evidence_coverage(
    plan: QuestionPlan,
    grades: Sequence[NeedEvidenceGrade],
) -> EvidenceCoverage:
    """中文：逐项对齐评分，并仅用 required Need 判断回答完整性。

    English: Align grades per need and use required needs only for answer completeness.
    """

    grade_by_need = {grade.need_id: grade for grade in grades}
    if len(grade_by_need) != len(grades):
        raise ValueError("evidence grades must contain unique need IDs")
    plan_need_ids = {need.id for need in plan.needs}
    if set(grade_by_need) != plan_need_ids:
        raise ValueError("evidence coverage requires exactly one grade for every plan need")
    required = [need for need in plan.needs if need.necessity is NeedNecessity.REQUIRED]
    supported = tuple(
        need.id for need in required if grade_by_need[need.id].status is EvidenceStatus.SUPPORTED
    )
    unresolved = tuple(
        need.id
        for need in required
        if grade_by_need[need.id].status is not EvidenceStatus.SUPPORTED
    )
    required_statuses = [grade_by_need[need.id].status for need in required]
    if all(status is EvidenceStatus.SUPPORTED for status in required_statuses):
        decision = EvidenceCoverageDecision.COMPLETE
    elif any(status is EvidenceStatus.CONFLICTING for status in required_statuses):
        decision = EvidenceCoverageDecision.CONFLICTING
    elif any(
        status in {EvidenceStatus.SUPPORTED, EvidenceStatus.PARTIALLY_SUPPORTED}
        for status in required_statuses
    ):
        decision = EvidenceCoverageDecision.PARTIAL
    elif any(status is EvidenceStatus.AMBIGUOUS for status in required_statuses):
        decision = EvidenceCoverageDecision.AMBIGUOUS
    else:
        decision = EvidenceCoverageDecision.INSUFFICIENT
    return EvidenceCoverage(
        grades=tuple(grades),
        decision=decision,
        supported_required_need_ids=supported,
        unresolved_required_need_ids=unresolved,
        optional_need_ids=tuple(
            need.id for need in plan.needs if need.necessity is NeedNecessity.OPTIONAL
        ),
    )
