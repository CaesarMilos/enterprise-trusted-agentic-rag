"""中文：验证时间槽位和最终断言不能被相似但不相关的法规证据替代。

English: Verify temporal slots and final claims cannot be supported by merely similar law text.
"""

from enterprise_rag.agent.citation_verifier import CitationVerifier
from enterprise_rag.agent.evidence_grader import EvidenceGrader
from enterprise_rag.domain.models import Chunk, RetrievalScope
from enterprise_rag.retrieval.models import (
    EvidenceBundle,
    EvidenceItem,
    RoutingResult,
    TopKDecision,
)


def _evidence(text: str) -> EvidenceBundle:
    """中文：构造包含一条法规证据的固定索引快照。

    English: Build a pinned snapshot containing one regulation evidence item.
    """

    chunk = Chunk(
        id="chunk-law",
        tenant_id="tenant-a",
        source_id="source-law",
        document_id="civil-code",
        document_version_id="version-a",
        ordinal=0,
        text=text,
        token_count=30,
        page_start=7,
        page_end=7,
        heading_path=("第一编 总则", "第二章 自然人"),
        previous_chunk_id=None,
        next_chunk_id=None,
        boundary_reason="article",
        chunker_version="regulation-structure-v5",
        content_hash="hash-law",
    )
    return EvidenceBundle(
        index_version_id="index-a",
        items=(EvidenceItem("C1", chunk, 1.0),),
        context_text=text,
        token_count=30,
        routing=RoutingResult(("source-law",), "single_source", "test"),
        top_k=TopKDecision(1, "test"),
    )


def _scope() -> RetrievalScope:
    """中文：构造允许访问法规来源的固定检索范围。

    English: Build a pinned retrieval scope authorized for the regulation source.
    """

    return RetrievalScope("tenant-a", frozenset({"source-law"}), index_version_id="index-a")


def test_temporal_need_rejects_guardianship_evidence() -> None:
    """中文：监护资格条文不能支撑自然人民事权利能力的起止时间。

    English: A guardianship rule cannot support when a natural person's civil capacity starts
    and ends.
    """

    evidence = _evidence("第三十八条 被监护人的父母可以申请恢复监护人资格。")

    grade = EvidenceGrader(minimum_coverage=0.1).grade(
        "自然人的民事权利能力从何时开始、何时终止？",
        evidence,
    )

    assert not grade.sufficient
    assert grade.missing_need_ids == ("need-1", "need-2")
    assert all("TEMPORAL_ROLE_NOT_FOUND" in item.missing_requirements for item in grade.need_grades)


def test_claim_verifier_rejects_birth_death_claim_with_wrong_citation() -> None:
    """中文：即使词面存在“自然人”，出生和死亡断言也不能引用不含时间规则的条文。

    English: Even with lexical similarity, a birth/death claim cannot cite a rule without those
    temporal semantics.
    """

    verification = CitationVerifier(minimum_claim_overlap=0.05).verify(
        "自然人的民事权利能力从出生时开始，到死亡时终止[C1]。",
        _evidence("第三十八条 被监护人的父母可以申请恢复监护人资格。"),
        _scope(),
    )

    assert not verification.valid
    assert "CLAIM_TIME_ROLE_NOT_IN_EVIDENCE" in verification.reason


def test_claim_verifier_accepts_article_thirteen_temporal_rule() -> None:
    """中文：民法典第十三条原文能够支撑出生至死亡的起止结论。

    English: Civil Code Article 13 can support the conclusion from birth until death.
    """

    verification = CitationVerifier(minimum_claim_overlap=0.2).verify(
        "自然人的民事权利能力从出生时开始，到死亡时终止[C1]。",
        _evidence(
            "第十三条 自然人从出生时起到死亡时止，具有民事权利能力，"
            "依法享有民事权利，承担民事义务。"
        ),
        _scope(),
    )

    assert verification.valid
