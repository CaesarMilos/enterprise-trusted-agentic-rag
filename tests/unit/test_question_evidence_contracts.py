"""中文：验证 QuestionPlan 和 required-only EvidenceCoverage 不变量。

English: Verify QuestionPlan and required-only EvidenceCoverage invariants.
"""

from enterprise_rag.core.enums import (
    AnswerFormat,
    EvidenceCoverageDecision,
    EvidenceStatus,
    InformationNeedIntent,
    NeedNecessity,
    NeedOrigin,
)
from enterprise_rag.domain.evidence import NeedEvidenceGrade, build_evidence_coverage
from enterprise_rag.domain.questions import (
    InformationNeed,
    QuestionPlan,
    ResponseContract,
    question_plan_fingerprint,
    validate_question_plan,
)


def _need(identifier: str, necessity: NeedNecessity) -> InformationNeed:
    """中文：构造不携带预期答案的通用信息需要。

    English: Build a generic information need containing no expected answer.
    """

    return InformationNeed(
        id=identifier,
        description=f"Need {identifier}",
        retrieval_query=f"Query {identifier}",
        necessity=necessity,
        origin=NeedOrigin.QUERY_DECOMPOSED,
        intent=InformationNeedIntent.SUMMARY,
    )


def _plan(needs: tuple[InformationNeed, ...]) -> QuestionPlan:
    """中文：创建具有确定性指纹的测试问题计划。

    English: Create a test question plan with a deterministic fingerprint.
    """

    contract = ResponseContract(requested_format=AnswerFormat.LIST)
    fingerprint = question_plan_fingerprint(
        "请分别说明这些内容并给出引用",
        "说明这些内容",
        contract,
        needs,
        (),
        "planner-v1",
    )
    return QuestionPlan(
        "question-plan-v1",
        "请分别说明这些内容并给出引用",
        "说明这些内容",
        contract,
        needs,
        (),
        "deterministic",
        "planner-v1",
        fingerprint,
    )


def test_optional_need_does_not_reduce_completeness() -> None:
    """中文：可选信息缺失不能制造错误的部分回答或拒答。

    English: A missing optional need cannot manufacture a partial answer or refusal.
    """

    required = _need("required", NeedNecessity.REQUIRED)
    optional = _need("optional", NeedNecessity.OPTIONAL)
    plan = _plan((required, optional))
    validate_question_plan(
        plan,
        max_total_needs=16,
        max_required_needs=12,
        max_anchors=32,
        max_dependency_depth=4,
    )
    coverage = build_evidence_coverage(
        plan,
        (
            NeedEvidenceGrade(
                "required",
                EvidenceStatus.SUPPORTED,
                supporting_evidence_ids=("ev-1",),
                coverage_score=1.0,
            ),
            NeedEvidenceGrade(
                "optional",
                EvidenceStatus.UNSUPPORTED,
                missing_requirements=("optional detail",),
            ),
        ),
    )
    assert coverage.decision is EvidenceCoverageDecision.COMPLETE


def test_partial_required_vector_produces_partial_decision() -> None:
    """中文：部分 required Need 有证据时产生 PARTIAL 而不是全局拒答。

    English: Some supported required needs produce PARTIAL rather than a global refusal.
    """

    first = _need("first", NeedNecessity.REQUIRED)
    second = _need("second", NeedNecessity.REQUIRED)
    plan = _plan((first, second))
    coverage = build_evidence_coverage(
        plan,
        (
            NeedEvidenceGrade(
                "first",
                EvidenceStatus.SUPPORTED,
                supporting_evidence_ids=("ev-1",),
                coverage_score=1.0,
            ),
            NeedEvidenceGrade(
                "second",
                EvidenceStatus.UNSUPPORTED,
                missing_requirements=("missing rule",),
            ),
        ),
    )
    assert coverage.decision is EvidenceCoverageDecision.PARTIAL
