"""中文：按 Information Need 评估证据覆盖，并以命题层约束判断关系。

English: Grade evidence per information need and judge proposition relationships with
subject, action, scope, condition, time, and modality constraints.
"""

from __future__ import annotations

from dataclasses import dataclass

from enterprise_rag.agent.proposition_extractor import required_temporal_roles, semantic_signals
from enterprise_rag.agent.question_planner import QuestionPlanner
from enterprise_rag.core.enums import ClaimModality, EvidenceStatus, PropositionRelationship
from enterprise_rag.domain.evidence import (
    EvidenceConflict,
    EvidenceCoverage,
    EvidenceProposition,
    NeedEvidenceGrade,
    build_evidence_coverage,
)
from enterprise_rag.domain.questions import InformationNeed, QuestionPlan
from enterprise_rag.indexing.bm25_index import lexical_tokens
from enterprise_rag.retrieval.identifier_normalizer import extract_exact_anchors
from enterprise_rag.retrieval.models import EvidenceBundle


@dataclass(frozen=True, slots=True)
class EvidenceGrade:
    """中文：保留 V4 简洁决策，同时携带 V5 按 Need 评分结果。

    English: Preserve the compact V4 decision while carrying V5 need-level grades.
    """

    sufficient: bool
    coverage: float
    conflicting: bool
    reason: str
    need_grades: tuple[NeedEvidenceGrade, ...] = ()
    missing_need_ids: tuple[str, ...] = ()


class PropositionRelationshipJudge:
    """中文：只在核心命题和适用范围重叠时判断模态冲突。

    English: Declare modality conflict only when the core claim and applicable scopes overlap.
    """

    _OPPOSITE_MODALITIES = frozenset(
        {
            frozenset({ClaimModality.REQUIRED, ClaimModality.PROHIBITED}),
            frozenset({ClaimModality.PERMITTED, ClaimModality.PROHIBITED}),
        }
    )

    def judge(self, left: EvidenceProposition, right: EvidenceProposition) -> EvidenceConflict:
        """中文：返回可审计关系；信息不足时标记 AMBIGUOUS 而不猜测。

        English: Return an auditable relationship and use AMBIGUOUS instead of guessing.
        """

        if left.exceptions or right.exceptions:
            relationship = PropositionRelationship.EXCEPTION
            reason = "EXPLICIT_EXCEPTION_SCOPE"
        elif not _same_core_claim(left, right):
            relationship = PropositionRelationship.DIFFERENT_SCOPE
            reason = "DIFFERENT_SUBJECT_ACTION_OR_OBJECT"
        elif not _scopes_overlap(left, right):
            relationship = PropositionRelationship.DIFFERENT_SCOPE
            reason = "NON_OVERLAPPING_CONDITION_TIME_OR_AUTHORITY"
        elif frozenset({left.modality, right.modality}) in self._OPPOSITE_MODALITIES:
            relationship = PropositionRelationship.CONFLICT
            reason = "SAME_SCOPE_OPPOSITE_MODALITY"
        elif None in (left.subject, left.predicate) or None in (right.subject, right.predicate):
            relationship = PropositionRelationship.AMBIGUOUS
            reason = "MISSING_CORE_PROPOSITION_FIELDS"
        else:
            relationship = PropositionRelationship.COMPATIBLE
            reason = "SAME_OR_COMPATIBLE_MODALITY"
        return EvidenceConflict(
            left_proposition_id=left.id,
            right_proposition_id=right.id,
            relationship=relationship,
            reason_code=reason,
            judge_method="deterministic-proposition-v1",
        )


class EvidenceGrader:
    """中文：用知识 Need 而非整句格式指令计算证据充分性。

    English: Determine sufficiency from knowledge needs rather than the formatted query.
    """

    def __init__(self, minimum_coverage: float = 0.35, minimum_items: int = 1) -> None:
        """中文：保存词汇覆盖和证据数量下限。

        English: Store lexical coverage and evidence-count thresholds.
        """

        if not 0.0 <= minimum_coverage <= 1.0:
            raise ValueError("minimum coverage must be within [0, 1]")
        self._minimum_coverage = minimum_coverage
        self._minimum_items = max(1, minimum_items)
        self._fallback_planner = QuestionPlanner()

    def grade(
        self,
        query: str,
        evidence: EvidenceBundle,
        plan: QuestionPlan | None = None,
    ) -> EvidenceGrade:
        """中文：评分每个 Need，并仅用 required Need 得出完整性决策。

        English: Grade each need and derive completeness from required needs only.
        """

        resolved_plan = plan or self._fallback_planner.plan(query)
        if len(evidence.items) < self._minimum_items:
            grades = tuple(
                NeedEvidenceGrade(
                    need_id=need.id,
                    status=EvidenceStatus.UNSUPPORTED,
                    missing_requirements=("NO_USABLE_EVIDENCE",),
                )
                for need in resolved_plan.needs
            )
            coverage = build_evidence_coverage(resolved_plan, grades)
            return self._legacy_projection(coverage, "No usable evidence was retrieved.")
        grades = tuple(
            self._grade_need(need, resolved_plan, evidence) for need in resolved_plan.needs
        )
        coverage = build_evidence_coverage(resolved_plan, grades)
        supported_count = len(coverage.supported_required_need_ids)
        required_count = supported_count + len(coverage.unresolved_required_need_ids)
        reason = (
            f"Supported {supported_count}/{required_count} required information need(s); "
            "presentation instructions were excluded from coverage."
        )
        return self._legacy_projection(coverage, reason)

    def grade_plan(self, plan: QuestionPlan, evidence: EvidenceBundle) -> EvidenceCoverage:
        """中文：返回供 V5 回答协议直接消费的完整 Need 覆盖向量。

        English: Return the full need-coverage vector consumed by the V5 answer protocol.
        """

        grades = tuple(self._grade_need(need, plan, evidence) for need in plan.needs)
        return build_evidence_coverage(plan, grades)

    def _grade_need(
        self,
        need: InformationNeed,
        plan: QuestionPlan,
        evidence: EvidenceBundle,
    ) -> NeedEvidenceGrade:
        """中文：基于 Need 词项和它引用的精确锚点选择支撑证据。

        English: Select support using need terms and only its referenced exact anchors.
        """

        need_terms = _meaningful_terms(need.retrieval_query)
        anchor_by_id = {anchor.id: anchor for anchor in plan.anchors}
        required_anchors = frozenset(
            anchor_by_id[anchor_id].normalized_value
            for anchor_id in need.anchor_ids
            if anchor_id in anchor_by_id
        )
        scored: list[tuple[float, str]] = []
        # 中文：问题中的时间角色必须在同一条候选证据中出现，不能跨不相关条文拼接。
        # English: Required temporal roles must occur in the same candidate evidence item.
        required_time_roles = required_temporal_roles(need.retrieval_query)
        anchor_supporting_ids: set[str] = set()
        for item in evidence.items:
            evidence_text = item.chunk.search_text
            evidence_terms = _meaningful_terms(evidence_text)
            item_anchors = frozenset(extract_exact_anchors(evidence_text))
            item_time_roles = semantic_signals(evidence_text).temporal_roles
            lexical_coverage = (
                len(need_terms & evidence_terms) / len(need_terms) if need_terms else 0.0
            )
            anchors_match = required_anchors <= item_anchors
            time_roles_match = required_time_roles <= item_time_roles
            if anchors_match:
                anchor_supporting_ids.add(item.citation_id)
            if lexical_coverage > 0.0 and time_roles_match and anchors_match:
                scored.append((lexical_coverage, item.citation_id))
        scored.sort(key=lambda item: (-item[0], item[1]))
        best_coverage = scored[0][0] if scored else 0.0
        anchors_covered = not required_anchors or bool(anchor_supporting_ids)
        supporting = tuple(
            citation_id for score, citation_id in scored if score >= self._minimum_coverage
        )
        partial = tuple(
            citation_id for score, citation_id in scored if 0.0 < score < self._minimum_coverage
        )
        missing: list[str] = []
        if not anchors_covered:
            missing.append("EXACT_ANCHOR_NOT_FOUND")
        if required_time_roles and not any(
            required_time_roles <= semantic_signals(item.chunk.search_text).temporal_roles
            for item in evidence.items
        ):
            missing.append("TEMPORAL_ROLE_NOT_FOUND")
        if best_coverage < self._minimum_coverage:
            missing.append("KNOWLEDGE_NEED_NOT_COVERED")
        if supporting and anchors_covered:
            status = EvidenceStatus.SUPPORTED
            missing = []
        elif supporting or partial:
            status = EvidenceStatus.PARTIALLY_SUPPORTED
        else:
            status = EvidenceStatus.UNSUPPORTED
        return NeedEvidenceGrade(
            need_id=need.id,
            status=status,
            supporting_evidence_ids=supporting if status is EvidenceStatus.SUPPORTED else (),
            partial_evidence_ids=(supporting + partial)
            if status is not EvidenceStatus.SUPPORTED
            else (),
            missing_requirements=tuple(missing),
            coverage_score=best_coverage,
            grading_method="deterministic-need-semantics-v5.1",
        )

    @staticmethod
    def _legacy_projection(coverage: EvidenceCoverage, reason: str) -> EvidenceGrade:
        """中文：把离散 Need 决策投影到现有编排器的简洁界面。

        English: Project discrete need decisions onto the compact orchestrator interface.
        """

        grades = coverage.grades
        score = sum(grade.coverage_score for grade in grades) / len(grades) if grades else 0.0
        conflicting = any(grade.status is EvidenceStatus.CONFLICTING for grade in grades)
        return EvidenceGrade(
            sufficient=not coverage.unresolved_required_need_ids and not conflicting,
            coverage=score,
            conflicting=conflicting,
            reason=reason,
            need_grades=grades,
            missing_need_ids=coverage.unresolved_required_need_ids,
        )


def _meaningful_terms(text: str) -> frozenset[str]:
    """中文：使用与 BM25 一致的双语分词，过滤无识别力单字。

    English: Use the BM25 bilingual tokenizer and discard uninformative one-character tokens.
    """

    return frozenset(term for term in lexical_tokens(text) if len(term) > 1 or ":" in term)


def _same_core_claim(left: EvidenceProposition, right: EvidenceProposition) -> bool:
    """中文：比较主体、谓词和对象；缺失值不能当作已知事实。

    English: Compare subject, predicate, and object without treating missing values as facts.
    """

    comparable = ((left.subject, right.subject), (left.predicate, right.predicate))
    if any(a is None or b is None for a, b in comparable):
        return True
    if any(_normalized(a) != _normalized(b) for a, b in comparable if a and b):
        return False
    if left.object is not None and right.object is not None:
        return _normalized(left.object) == _normalized(right.object)
    return True


def _scopes_overlap(left: EvidenceProposition, right: EvidenceProposition) -> bool:
    """中文：只有已知条件、时间和权限范围不互斥时才认为可能重叠。

    English: Treat scopes as overlapping only when known condition, time, and authority do not
    contradict.
    """

    if left.conditions and right.conditions:
        left_conditions = {_normalized(value) for value in left.conditions}
        right_conditions = {_normalized(value) for value in right.conditions}
        if not left_conditions & right_conditions:
            return False
    for left_value, right_value in (
        (left.temporal_scope, right.temporal_scope),
        (left.authority_scope, right.authority_scope),
    ):
        if left_value and right_value and _normalized(left_value) != _normalized(right_value):
            return False
    return True


def _normalized(value: str) -> str:
    """中文：为确定性比较折叠大小写和空白。

    English: Fold case and whitespace for deterministic comparison.
    """

    return " ".join(value.casefold().split())
