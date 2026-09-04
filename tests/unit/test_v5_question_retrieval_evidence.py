"""中文：验证 V5 通用问题计划、Need-aware Top-K、局部窗口和命题关系。

English: Verify generic V5 question planning, need-aware Top-K, local windows, and proposition
relationships.
"""

from enterprise_rag.agent.evidence_grader import PropositionRelationshipJudge
from enterprise_rag.agent.question_planner import QuestionPlanner
from enterprise_rag.core.enums import ClaimModality, PropositionRelationship
from enterprise_rag.domain.evidence import EvidenceProposition
from enterprise_rag.domain.models import Chunk
from enterprise_rag.retrieval.dynamic_top_k import DynamicTopK
from enterprise_rag.retrieval.models import RetrievalCandidate
from enterprise_rag.retrieval.parent_expander import ParentExpander


def _chunk(
    identifier: str,
    ordinal: int,
    text: str,
    *,
    parent_id: str | None = "parent-a",
    previous_id: str | None = None,
    next_id: str | None = None,
    hard_boundary: str | None = "rule-a",
    level: str = "leaf",
    tokens: int = 10,
) -> Chunk:
    """中文：构造具有可控邻接和硬边界的文本块。

    English: Build a chunk with controlled adjacency and hard-boundary metadata.
    """

    return Chunk(
        id=identifier,
        tenant_id="tenant-a",
        source_id="source-a",
        document_id="document-a",
        document_version_id="version-a",
        ordinal=ordinal,
        text=text,
        token_count=tokens,
        page_start=1,
        page_end=1,
        heading_path=("Section",),
        previous_chunk_id=previous_id,
        next_chunk_id=next_id,
        boundary_reason="test",
        chunker_version="test-v1",
        content_hash=f"hash-{identifier}",
        parent_chunk_id=parent_id,
        chunk_level=level,
        hard_boundary_key=hard_boundary,
    )


def _proposition(
    identifier: str,
    predicate: str,
    modality: ClaimModality,
    *,
    condition: str = "normal operation",
) -> EvidenceProposition:
    """中文：构造可追溯的测试命题。

    English: Build one traceable test proposition.
    """

    return EvidenceProposition(
        id=identifier,
        subject="operator",
        predicate=predicate,
        object="device",
        modality=modality,
        conditions=(condition,),
        exceptions=(),
        temporal_scope="v1",
        authority_scope="plant-a",
        source_chunk_id=f"chunk-{identifier}",
        source_span_start=0,
        source_span_end=10,
        extraction_method="deterministic-test",
    )


def test_question_planner_excludes_format_instructions_and_preserves_anchor() -> None:
    """中文：格式词不进入知识查询，条款锚点仍被保留。

    English: Format phrases stay out of the knowledge query while exact anchors remain.
    """

    plan = QuestionPlanner().plan("根据文档，请回答并给出引用：第八条有什么限制？")

    assert "请回答" not in plan.knowledge_query
    assert tuple(anchor.normalized_value for anchor in plan.anchors) == ("clause:8",)
    assert plan.response_contract.citation_required


def test_requested_cardinality_expands_top_k_without_inventing_semantic_needs() -> None:
    """中文：“六项”扩展候选数，但不伪造六个未命名 Need。

    English: “Six items” expands candidate coverage without inventing six unnamed needs.
    """

    plan = QuestionPlanner().plan("请分别列出设备操作的六项安全原则并引用")
    chunks = {
        f"chunk-{index}": _chunk(
            f"chunk-{index}",
            index,
            f"设备操作安全原则 {index}",
            parent_id=None,
            hard_boundary=f"rule-{index}",
        )
        for index in range(8)
    }
    candidates = tuple(
        RetrievalCandidate(f"chunk-{index}", 1.0 - index / 100) for index in range(8)
    )

    selected, decision = DynamicTopK(2, 3, 8, 200).select(candidates, chunks, plan)

    assert len(plan.needs) == 1
    assert len(selected) == 6
    assert decision.selected_k == 6


def test_parallel_requirement_and_prohibition_are_not_automatically_conflicting() -> None:
    """中文：不同行为的“应当”和“不得”是并列规则，不是冲突。

    English: Requirement and prohibition about different actions are parallel rules, not conflict.
    """

    relationship = PropositionRelationshipJudge().judge(
        _proposition("left", "inspect", ClaimModality.REQUIRED),
        _proposition("right", "bypass", ClaimModality.PROHIBITED),
    )

    assert relationship.relationship is PropositionRelationship.DIFFERENT_SCOPE


def test_same_claim_same_scope_opposite_modalities_conflict() -> None:
    """中文：同主体、行为、对象、条件和时间下的相反模态才是冲突。

    English: Opposite modalities conflict only for the same claim and applicable scope.
    """

    relationship = PropositionRelationshipJudge().judge(
        _proposition("left", "restart", ClaimModality.REQUIRED),
        _proposition("right", "restart", ClaimModality.PROHIBITED),
    )

    assert relationship.relationship is PropositionRelationship.CONFLICT


def test_oversized_parent_falls_back_to_same_boundary_local_window() -> None:
    """中文：超大 Parent 回退为同硬边界的前一块、命中块和后一块。

    English: An oversized parent falls back to previous-hit-next within one hard boundary.
    """

    previous = _chunk("previous", 0, "Preparation", next_id="hit")
    hit = _chunk("hit", 1, "Required action", previous_id="previous", next_id="next")
    following = _chunk("next", 2, "Expected result", previous_id="hit")
    parent = _chunk(
        "parent-a",
        0,
        "Oversized section",
        parent_id=None,
        hard_boundary="rule-a",
        level="parent",
        tokens=80,
    )
    stored = {item.id: item for item in (previous, hit, following, parent)}

    result = ParentExpander(50, 100).expand(
        "tenant-a",
        (RetrievalCandidate("hit", 1.0),),
        {"hit": hit},
        lambda tenant_id, ids: tuple(stored[item] for item in ids if item in stored),
    )

    assert result.contexts["hit"].chunk_level == "local_window"
    assert result.contexts["hit"].text == "Preparation\n\nRequired action\n\nExpected result"


def test_need_quota_prefers_temporally_qualified_evidence() -> None:
    """中文：起止时间 Need 的预留配额必须选择含对应时间角色的条文。

    English: Reserved quota for start/end needs must choose evidence containing those roles.
    """

    plan = QuestionPlanner().plan("自然人的民事权利能力从何时开始、何时终止？")
    chunks = {
        "wrong": _chunk(
            "wrong",
            0,
            "自然人的民事权利受到法律保护。",
            parent_id=None,
            hard_boundary="article:38",
        ),
        "right": _chunk(
            "right",
            1,
            "自然人从出生时起到死亡时止，具有民事权利能力。",
            parent_id=None,
            hard_boundary="article:13",
        ),
    }
    candidates = (RetrievalCandidate("wrong", 1.0), RetrievalCandidate("right", 0.8))

    selected, decision = DynamicTopK(1, 2, 4, 200).select(candidates, chunks, plan)

    assert selected[0].chunk_id == "right"
    assert decision.covered_need_ids == ("need-1", "need-2")
