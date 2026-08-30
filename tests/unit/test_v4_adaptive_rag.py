"""中文：验证 V4 自适应边界、中文切句、Child 索引与 Parent 扩展核心算法。

English: Verify V4 adaptive boundaries, Chinese splitting, child indexing, and parent expansion.
"""

from __future__ import annotations

from enterprise_rag.domain.models import Chunk, Source
from enterprise_rag.indexing.models import IndexBuildPlan
from enterprise_rag.ingestion.chunking.boundary_scorer import (
    AdaptiveBoundaryScorer,
    BoundaryFeatures,
)
from enterprise_rag.ingestion.chunking.chinese_sentence_splitter import ChineseSentenceSplitter
from enterprise_rag.retrieval.models import RetrievalCandidate
from enterprise_rag.retrieval.parent_expander import ParentExpander


def _chunk(
    chunk_id: str,
    text: str,
    *,
    level: str = "leaf",
    parent_id: str | None = None,
    tokens: int = 20,
) -> Chunk:
    """中文：构造同一租户文档版本下的最小 Chunk 测试对象。

    English: Build a minimal chunk under one tenant-owned immutable document version.
    """

    return Chunk(
        id=chunk_id,
        tenant_id="tenant-a",
        source_id="source-a",
        document_id="document-a",
        document_version_id="version-a",
        ordinal=0,
        text=text,
        token_count=tokens,
        page_start=1,
        page_end=1,
        heading_path=("安装",),
        previous_chunk_id=None,
        next_chunk_id=None,
        boundary_reason="test",
        chunker_version="v4-test",
        content_hash=f"hash-{chunk_id}",
        retrieval_text=f"安装\n{text}",
        parent_chunk_id=parent_id,
        chunk_level=level,
    )


def test_dynamic_boundary_threshold_changes_with_length_pressure() -> None:
    """中文：确认短块更难切、超过目标后更容易切，硬 max 由调用方强制执行。

    English: Ensure short chunks resist splitting and over-target chunks split more readily.
    """

    scorer = AdaptiveBoundaryScorer(min_tokens=100, target_tokens=300, max_tokens=600)
    features = BoundaryFeatures(0.4, 0.7, 0.0, 0.2, 0.3)

    short = scorer.score(features, 50)
    target = scorer.score(features, 300)
    long = scorer.score(
        BoundaryFeatures(0.4, 0.7, scorer.length_pressure(520), 0.2, 0.3),
        520,
    )

    assert short.threshold > target.threshold > long.threshold
    assert not short.should_split
    assert long.should_split


def test_chinese_sentence_splitter_preserves_decimal_and_url() -> None:
    """中文：确认版本号、小数和 URL 中的句点不会被误判为句末。

    English: Ensure periods in versions, decimals, and URLs are not mistaken for sentence ends.
    """

    parts = ChineseSentenceSplitter().split(
        "请安装 v2.3.1，阈值为 0.75。访问 https://example.com/a.b 获取说明！"
    )

    assert parts == (
        "请安装 v2.3.1，阈值为 0.75。",
        "访问 https://example.com/a.b 获取说明！",
    )


def test_index_plan_contains_only_leaf_chunks() -> None:
    """中文：确认 Parent 不进入 BM25/向量候选池，避免挤占精确 Child 命中。

    English: Ensure parents never enter BM25/vector candidates and displace precise children.
    """

    leaf = _chunk("child-a", "断开电源", parent_id="parent-a")
    parent = _chunk("parent-a", "维护前必须断开电源并检查指示灯", level="parent")
    plan = IndexBuildPlan.from_domain(
        "index-a",
        "tenant-a",
        (parent, leaf),
        (Source("source-a", "tenant-a", "Manual", "Device manual"),),
        "v4-test",
        "embedding-test",
        "config-test",
    )

    assert tuple(entry.chunk_id for entry in plan.entries) == ("child-a",)


def test_parent_expansion_keeps_child_citation_identity() -> None:
    """中文：确认 Parent 在预算内作为上下文展开，而映射键仍是精确 Child ID。

    English: Ensure an in-budget parent expands as context while the key remains the child ID.
    """

    child = _chunk("child-a", "断开电源", parent_id="parent-a", tokens=8)
    parent = _chunk(
        "parent-a",
        "维护前必须断开电源并检查指示灯",
        level="parent",
        tokens=30,
    )
    expander = ParentExpander(max_parent_tokens=40, context_token_budget=50)

    result = expander.expand(
        "tenant-a",
        (RetrievalCandidate("child-a", 1.0),),
        {child.id: child},
        lambda _tenant, _ids: (parent,),
    )

    assert result.contexts["child-a"].id == "parent-a"
    assert result.expanded_parent_ids == ("parent-a",)
    assert result.token_count == 30
