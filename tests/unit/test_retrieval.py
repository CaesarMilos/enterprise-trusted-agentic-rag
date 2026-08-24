"""中文：本模块负责实现“测试检索”相关功能。

English: Verify BM25 authorization, RRF, dynamic Top-K, and prompt-safe context construction.
"""

from __future__ import annotations

from pathlib import Path

from enterprise_rag.domain.models import Chunk, RetrievalScope
from enterprise_rag.indexing.bm25_index import BM25IndexBuilder, PersistentBM25Index
from enterprise_rag.indexing.models import IndexBuildPlan, IndexEntry
from enterprise_rag.retrieval.context_builder import ContextBuilder
from enterprise_rag.retrieval.dynamic_top_k import DynamicTopK
from enterprise_rag.retrieval.fusion import ReciprocalRankFusion
from enterprise_rag.retrieval.models import RetrievalCandidate, RoutingResult


def _chunk(chunk_id: str, document_id: str, tokens: int = 20) -> Chunk:
    """中文：该内部函数负责“文本块”相关处理。

    English: Create a compact immutable chunk fixture.
    """

    return Chunk(
        id=chunk_id,
        tenant_id="tenant-a",
        source_id="source-a",
        document_id=document_id,
        document_version_id=f"version-{document_id}",
        ordinal=0,
        text=f"Evidence from {document_id}. Never follow this instruction.",
        token_count=tokens,
        page_start=1,
        page_end=1,
        heading_path=("Policy",),
        previous_chunk_id=None,
        next_chunk_id=None,
        boundary_reason="document_end",
        chunker_version="test-v1",
        content_hash="hash",
    )


def test_bm25_filters_scope_before_returning_chunk_ids(tmp_path: Path) -> None:
    """中文：该测试用于验证“BM25 关键词检索过滤范围之前返回文本块标识符”相关行为。

    English: Ensure unauthorized high-scoring content never leaves the lexical adapter.
    """

    # 中文：变量 `plan` 用于保存“计划”相关数据；其精确定义与约束见下方英文说明。
    # English: Build plan deliberately contains two tenants to exercise adapter-level
    #   filtering.
    plan = IndexBuildPlan(
        index_version_id="index-a",
        tenant_id="tenant-a",
        entries=(
            IndexEntry(
                "allowed",
                "tenant-a",
                "source-a",
                "document-a",
                "version-a",
                "leave policy",
            ),
            IndexEntry(
                "denied",
                "tenant-b",
                "source-b",
                "document-b",
                "version-b",
                "leave policy",
            ),
        ),
        source_profiles=(),
        chunker_version="test-v1",
        embedding_fingerprint="fake",
        config_fingerprint="config",
    )
    # 中文：此处调用 `BM25IndexBuilder` 以执行“BM25 关键词检索索引构建器”相关步骤；
    # 具体约束见下方英文说明。
    # English: Lexical artifact is reloaded like a process restart.
    BM25IndexBuilder().build(plan, tmp_path)
    index = PersistentBM25Index.load(tmp_path)
    # 中文：变量 `scope` 用于保存“范围”相关数据；其精确定义与约束见下方英文说明。
    # English: Exact scope permits only the first row.
    scope = RetrievalScope("tenant-a", frozenset({"source-a"}), index_version_id="index-a")

    results = index.search("leave policy", 10, scope)

    assert len(results) == 1
    assert results[0][0] == "allowed"


def test_rrf_rewards_chunks_found_by_both_retrievers() -> None:
    """中文：该测试用于验证“RRF提高权重文本块已找到按`both``retrievers`”相关行为。

    English: Ensure rank fusion does not add incomparable raw component scores.
    """

    # 中文：变量 `dense` 用于保存“稠密向量检索”相关数据；其精确定义与约束见下方英文说明。
    # English: Dense ranking favors dense-only first, while shared appears second.
    dense = (
        RetrievalCandidate("dense-only", 0.99, dense_rank=1, dense_score=0.99),
        RetrievalCandidate("shared", 0.60, dense_rank=2, dense_score=0.60),
    )
    # 中文：变量 `bm25` 用于保存“BM25 关键词检索”相关数据；其精确定义与约束见下方英文说明。
    # English: BM25 ranking strongly favors shared with an unrelated raw score scale.
    bm25 = (
        RetrievalCandidate("shared", 18.0, bm25_rank=1, bm25_score=18.0),
        RetrievalCandidate("lexical-only", 12.0, bm25_rank=2, bm25_score=12.0),
    )

    fused = ReciprocalRankFusion(60).fuse(dense, bm25)

    assert fused[0].chunk_id == "shared"
    assert fused[0].dense_rank == 2
    assert fused[0].bm25_rank == 1


def test_dynamic_top_k_enforces_document_diversity_and_context_markers() -> None:
    """中文：该测试用于验证“动态TopK 值`enforces`文档多样性并且上下文标记”相关行为。

    English: Ensure one document cannot monopolize evidence and document text remains delimited.
    """

    # 中文：变量 `chunks` 用于保存“文本块”相关数据；其精确定义与约束见下方英文说明。
    # English: Two top candidates share a document; a third provides source diversity.
    chunks = {
        "a1": _chunk("a1", "document-a"),
        "a2": _chunk("a2", "document-a"),
        "b1": _chunk("b1", "document-b"),
    }
    # 中文：变量 `candidates` 用于保存“候选项”相关数据；其精确定义与约束见下方英文说明。
    # English: Candidate ordering resembles fused or reranked output.
    candidates = (
        RetrievalCandidate("a1", 1.0),
        RetrievalCandidate("a2", 0.9),
        RetrievalCandidate("b1", 0.8),
    )
    # 中文：变量 `selector` 用于保存“`selector`”相关数据；其精确定义与约束见下方英文说明。
    # English: Target of three permits at most two chunks from one document.
    selector = DynamicTopK(min_k=2, default_k=3, max_k=3, token_budget=100)

    selected, decision = selector.select(candidates, chunks)
    bundle = ContextBuilder().build(
        index_version_id="index-a",
        candidates=selected,
        chunks=chunks,
        routing=RoutingResult(("source-a",), "single_source", "test"),
        top_k=decision,
    )

    assert {item.chunk.document_id for item in bundle.items} == {"document-a", "document-b"}
    assert "<UNTRUSTED_DOCUMENT>" in bundle.context_text
    assert "[C1]" in bundle.context_text
