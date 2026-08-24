"""中文：验证 V0.3 PDF 恢复、自适应层级切块、中文锚点和检索安全回退。

English: Verify V0.3 PDF reflow, adaptive hierarchy, Chinese anchors, and safe retrieval
fallbacks.
"""

from __future__ import annotations

from dataclasses import replace

from enterprise_rag.agent.citation_verifier import CitationVerifier
from enterprise_rag.agent.evidence_grader import EvidenceGrader
from enterprise_rag.core.enums import ContentProfile
from enterprise_rag.domain.models import Chunk, RetrievalScope
from enterprise_rag.indexing.bm25_index import lexical_tokens
from enterprise_rag.ingestion.boundary_analyzer import (
    AdaptiveBoundaryAnalyzer,
    BoundaryDecision,
    BoundaryReviewBudget,
)
from enterprise_rag.ingestion.chunk_strategies import build_default_strategy_registry
from enterprise_rag.ingestion.cleaner import TextCleaner
from enterprise_rag.ingestion.loaders.base import LoadedDocument, RawBlock
from enterprise_rag.ingestion.semantic_chunker import ChunkingContext, DynamicSemanticChunker
from enterprise_rag.ingestion.structure_parser import (
    StructureParser,
    StructuredUnit,
    estimate_tokens,
)
from enterprise_rag.retrieval.dynamic_top_k import DynamicTopK
from enterprise_rag.retrieval.models import (
    EvidenceBundle,
    EvidenceItem,
    RetrievalCandidate,
    RetrievalQuery,
    RoutingResult,
    TopKDecision,
)
from enterprise_rag.retrieval.source_router import SourceRouter


class _AmbiguousSimilarity:
    """中文：为每个候选位置返回固定模糊相似度。

    English: Return a fixed ambiguous similarity at every candidate position.
    """

    def similarity(self, _left: str, _right: str) -> float:
        """中文：返回恰好位于 LLM 复核区间中心的分数。

        English: Return a score exactly at the center of the LLM review band.
        """

        return 0.52


class _CountingBoundaryJudge:
    """中文：记录测试期间实际发生的 LLM 边界复核次数。

    English: Count the LLM boundary reviews actually performed during a test.
    """

    def __init__(self) -> None:
        """中文：初始化零次调用计数器。

        English: Initialize the call counter at zero.
        """

        self.calls = 0

    def decide(self, _left: str, _right: str) -> BoundaryDecision:
        """中文：记录调用并要求继续合并文本。

        English: Record the call and request continued text aggregation.
        """

        self.calls += 1
        return BoundaryDecision(False, "llm_boundary", 0.8)


class _InvalidBoundaryJudge:
    """中文：模拟模型已被调用但 JSON 输出无法解析的情况。

    English: Model a completed provider call whose JSON output cannot be parsed.
    """

    def __init__(self) -> None:
        """中文：初始化真实模型请求计数。

        English: Initialize the real provider-request counter.
        """

        self.calls = 0

    def decide(self, _left: str, _right: str) -> BoundaryDecision | None:
        """中文：记录请求并返回解析失败结果。

        English: Record the request and return the parse-failure result.
        """

        self.calls += 1
        return None


class _FailingSimilarity:
    """中文：模拟不可用的外部向量提供方。

    English: Model an unavailable external embedding-similarity provider.
    """

    def similarity(self, _left: str, _right: str) -> float:
        """中文：抛出稳定异常以验证确定性降级。

        English: Raise a stable failure to verify deterministic degradation.
        """

        raise RuntimeError("embedding provider unavailable")


def _context() -> ChunkingContext:
    """中文：返回测试共享的固定 Chunk 身份上下文。

    English: Return the fixed chunk identity context shared by tests.
    """

    return ChunkingContext("tenant-a", "source-a", "document-a", "version-a")


def _unit(text: str, kind: str, heading: tuple[str, ...]) -> StructuredUnit:
    """中文：构建保留结构和检索文本的紧凑单元。

    English: Build a compact unit retaining structure and retrieval text.
    """

    return StructuredUnit(
        text=text,
        kind=kind,
        heading_path=heading,
        page_number=1,
        token_count=estimate_tokens(text),
        section_number=text.split(maxsplit=1)[0] if kind == "numbered_clause" else None,
        retrieval_text=text,
    )


def _chunk(chunk_id: str, document_id: str, text: str = "有效条件证据") -> Chunk:
    """中文：构建用于检索、证据和引用测试的完整叶子块。

    English: Build one complete leaf chunk for retrieval, evidence, and citation tests.
    """

    return Chunk(
        id=chunk_id,
        tenant_id="tenant-a",
        source_id="source-a",
        document_id=document_id,
        document_version_id=f"version-{document_id}",
        ordinal=0,
        text=text,
        token_count=estimate_tokens(text),
        page_start=24,
        page_end=24,
        heading_path=("第一百四十三条",),
        previous_chunk_id=None,
        next_chunk_id=None,
        boundary_reason="document_end",
        chunker_version="test-v2",
        content_hash="hash",
        retrieval_text=f"第一百四十三条 {text}",
    )


def test_llm_boundary_reviews_are_bounded_per_document() -> None:
    """中文：确认长文档的模糊切点不会触发无限次 LLM 调用。

    English: Ensure ambiguous boundaries in a long document cannot trigger unlimited LLM calls.
    """

    judge = _CountingBoundaryJudge()
    analyzer = AdaptiveBoundaryAnalyzer(
        min_tokens=1,
        target_tokens=1,
        max_tokens=100,
        hard_boundary_kinds=frozenset(),
        similarity_provider=_AmbiguousSimilarity(),
        llm_judge=judge,  # type: ignore[arg-type]
    )
    chunker = DynamicSemanticChunker(
        1,
        1,
        100,
        "bounded-llm-v1",
        boundary_analyzer=analyzer,
        create_parent_chunks=False,
        max_llm_boundaries=2,
    )
    units = tuple(_unit(f"连续说明文字{index}", "paragraph", ()) for index in range(8))

    chunks = chunker.chunk(units, _context())

    assert chunks
    assert judge.calls == 2


def test_invalid_llm_results_still_consume_the_document_budget() -> None:
    """中文：确认坏 JSON 无法绕过每文档两次的真实请求上限。

    English: Ensure invalid JSON cannot bypass the two-request document budget.
    """

    judge = _InvalidBoundaryJudge()
    analyzer = AdaptiveBoundaryAnalyzer(
        min_tokens=1,
        target_tokens=1,
        max_tokens=100,
        hard_boundary_kinds=frozenset(),
        similarity_provider=_AmbiguousSimilarity(),
        llm_judge=judge,  # type: ignore[arg-type]
    )
    chunker = DynamicSemanticChunker(
        1,
        1,
        100,
        "invalid-json-budget-v1",
        boundary_analyzer=analyzer,
        create_parent_chunks=False,
        max_llm_boundaries=2,
    )
    units = tuple(_unit(f"模糊切点{index}", "paragraph", ()) for index in range(8))

    chunks = chunker.chunk(units, _context())

    assert judge.calls == 2
    assert any(chunk.metadata["fallback_reason"] == "llm_invalid_json" for chunk in chunks)
    assert max(int(chunk.metadata["llm_calls_used"]) for chunk in chunks) == 2


def test_similarity_provider_failure_uses_lexical_fallback() -> None:
    """中文：确认向量提供方异常不会终止切块。

    English: Ensure an embedding-provider exception cannot terminate chunking.
    """

    analyzer = AdaptiveBoundaryAnalyzer(
        min_tokens=1,
        target_tokens=1,
        max_tokens=100,
        hard_boundary_kinds=frozenset(),
        similarity_provider=_FailingSimilarity(),
    )
    decision = analyzer.decide(
        (_unit("完全不同的左侧主题", "paragraph", ()),),
        10,
        _unit("右侧设备故障处理", "paragraph", ()),
        review_budget=BoundaryReviewBudget(0),
    )

    assert decision.fallback_reason == "embedding_provider_error"
    assert decision.method.startswith("lexical_fallback_")


def test_civil_code_pdf_reflow_keeps_clause_and_subitems_together() -> None:
    """中文：确认法典式孤立编号和标点恢复后，第一百四十三条保持完整可检索。

    English: Ensure isolated legal markers reflow into one complete and retrievable clause.
    """

    raw_text = """第三节
民事法律行为的效力
第一百四十三条
具备下列条件的民事法律行为有效
；
（
一
）
行为人具有相应的民事行为能力
；
（
二
）
意思表示真实
；
（
三
）
不违反法律
、
行政法规的强制性规定
，
不违背公序良俗
。
第一百四十四条
无民事行为能力人实施的民事法律行为无效
。"""
    loaded = LoadedDocument(
        "civil-code.pdf",
        "pdf",
        (RawBlock(raw_text, "page", 24),),
    )
    units = StructureParser().parse(TextCleaner().clean(loaded))
    strategy = build_default_strategy_registry(40, 80, 140).resolve(
        ContentProfile.GENERAL_PROSE
    )
    chunks = strategy.chunk(units, _context())

    clause = next(chunk for chunk in chunks if chunk.section_number == "第一百四十三条")
    assert "(一)行为人具有相应的民事行为能力" in clause.text
    assert "(二)意思表示真实" in clause.text
    assert "(三)不违反法律、行政法规的强制性规定" in clause.text
    assert "clause:143" in lexical_tokens(clause.retrieval_text)


def test_markdown_heading_is_indexed_and_remains_a_hard_boundary() -> None:
    """中文：确认短 Markdown 章节不会跨一级标题合并，且标题进入检索文本。

    English: Ensure short Markdown sections do not merge across top headings and headings are
    searchable.
    """

    loaded = LoadedDocument(
        "guide.md",
        "md",
        (
            RawBlock("Alpha Section", "heading", heading_level=1),
            RawBlock("Short alpha body.", "paragraph"),
            RawBlock("Beta Section", "heading", heading_level=1),
            RawBlock("Short beta body.", "paragraph"),
        ),
    )
    units = StructureParser().parse(TextCleaner().clean(loaded))
    chunks = build_default_strategy_registry(3, 20, 80).resolve(
        ContentProfile.GENERAL_PROSE
    ).chunk(units, _context())
    leaves = tuple(chunk for chunk in chunks if chunk.chunk_level == "leaf")

    assert len(leaves) == 2
    assert "Alpha Section" in leaves[0].retrieval_text
    assert "Beta Section" in leaves[1].retrieval_text


def test_manual_steps_generate_parent_child_context() -> None:
    """中文：确认同一说明书章节的连续步骤生成叶子块和 Token 有界父块。

    English: Ensure consecutive manual steps create leaves and a token-bounded parent context.
    """

    heading = ("安装流程",)
    units = (
        _unit("安装流程", "heading", heading),
        _unit("步骤1 关闭电源。", "step", heading),
        _unit("步骤2 连接接地线。", "step", heading),
        _unit("步骤3 检查指示灯。", "step", heading),
    )
    chunks = build_default_strategy_registry(3, 20, 100).resolve(ContentProfile.MANUAL).chunk(
        units,
        _context(),
    )
    parents = tuple(chunk for chunk in chunks if chunk.chunk_level == "parent")
    leaves = tuple(chunk for chunk in chunks if chunk.chunk_level == "leaf")

    assert parents
    assert any(chunk.parent_chunk_id == parents[0].id for chunk in leaves)


def test_single_document_top_k_does_not_apply_diversity_half_cap() -> None:
    """中文：确认候选仅来自唯一正确文档时，Top-K 可以选满目标数量。

    English: Ensure Top-K can fill its target when every candidate belongs to the only document.
    """

    chunks = {f"c{index}": _chunk(f"c{index}", "document-a") for index in range(4)}
    candidates = tuple(
        RetrievalCandidate(f"c{index}", 1.0 - index * 0.05) for index in range(4)
    )
    selected, decision = DynamicTopK(3, 4, 4, 1000).select(candidates, chunks)

    assert len(selected) == 4
    assert decision.selected_k == 4


def test_ambiguous_chinese_source_routing_falls_back_to_all_authorized_sources() -> None:
    """中文：确认多个资料源仅共享同一中文词组时，不会固定丢弃排序靠后的正确来源。

    English: Ensure tied CJK source signals do not discard a later authorized source.
    """

    scope = RetrievalScope(
        "tenant-a",
        frozenset(f"source-{index}" for index in range(5)),
        index_version_id="index-a",
    )
    query = RetrievalQuery("设备故障", "设备故障", scope)
    profiles = tuple(
        {
            "source_id": f"source-{index}",
            "name": "设备资料",
            "description": "设备故障资料",
            "profile_terms": ("设备", "故障"),
        }
        for index in range(5)
    )

    routed = SourceRouter(max_sources=4).route(query, profiles)

    assert routed.mode == "authorized_global"
    assert set(routed.source_ids) == scope.source_ids


def test_exact_clause_anchor_is_required_by_evidence_grade() -> None:
    """中文：确认普通词覆盖不能替代查询中的精确条款号。

    English: Ensure general lexical coverage cannot substitute for an exact clause identifier.
    """

    chunk = _chunk("c1", "document-a", "行为人具有相应的民事行为能力")
    # 中文：故意删除第一百四十三条检索前缀，构造编号不匹配证据。
    # English: Deliberately remove the clause prefix to create identifier-mismatched evidence.
    chunk = replace(chunk, retrieval_text=chunk.text)
    evidence = EvidenceBundle(
        "index-a",
        (EvidenceItem("C1", chunk, 1.0),),
        chunk.text,
        chunk.token_count,
        RoutingResult(("source-a",), "single_source", "test"),
        TopKDecision(1, "test"),
    )

    grade = EvidenceGrader(minimum_coverage=0.1).grade(
        "第一百四十三条行为人需要什么能力？",
        evidence,
    )

    assert not grade.sufficient


def test_citation_excerpt_is_centered_on_supported_claim() -> None:
    """中文：确认引用摘录定位到 Chunk 后部的支撑语句，而不是固定显示开头。

    English: Ensure citation excerpts center on a supporting sentence near the chunk end.
    """

    target = "意思表示真实是民事法律行为有效的条件。"
    chunk = _chunk("c1", "document-a", f"{'无关前文。' * 80}{target}")
    scope = RetrievalScope("tenant-a", frozenset({"source-a"}), index_version_id="index-a")
    evidence = EvidenceBundle(
        "index-a",
        (EvidenceItem("C1", chunk, 1.0),),
        chunk.text,
        chunk.token_count,
        RoutingResult(("source-a",), "single_source", "test"),
        TopKDecision(1, "test"),
    )

    verification = CitationVerifier(minimum_claim_overlap=0.1).verify(
        "意思表示真实是有效条件[C1]。",
        evidence,
        scope,
    )

    assert verification.valid
    assert target in (verification.citations[0].excerpt or "")
