"""中文：本模块实现法规专用的法条硬边界切分策略。

English: Implement regulation-specific chunking with article-level hard boundaries.
"""

from __future__ import annotations

import re

from enterprise_rag.core.enums import ContentProfile
from enterprise_rag.domain.models import Chunk
from enterprise_rag.ingestion.boundary_analyzer import (
    AdaptiveBoundaryAnalyzer,
    LLMBoundaryJudge,
    SimilarityProvider,
)
from enterprise_rag.ingestion.chunking.boundary_scorer import BoundaryWeights
from enterprise_rag.ingestion.semantic_chunker import ChunkingContext, DynamicSemanticChunker
from enterprise_rag.ingestion.structure_parser import StructuredUnit

# 中文：法条锚点允许中文数字、阿拉伯数字及 PDF 重排产生的内部空格。
# English: Article anchors accept Chinese/Arabic numerals and PDF-reflow whitespace.
_ARTICLE_PATTERN = re.compile(
    r"^第\s*[零〇一二两三四五六七八九十百千万亿0-9]+\s*条"
)
# 中文：编、章、节只参与紧凑标题路径，不与法条共享硬边界键。
# English: Parts, chapters, and sections form compact headings without sharing article keys.
_HEADING_PATTERN = re.compile(
    r"^第\s*[零〇一二两三四五六七八九十百千万亿0-9]+\s*[编章节]"
)
# 中文：款项标记保留为法条内部结构，不启动新的法条边界。
# English: Sub-clause markers remain internal article structure and do not start new articles.
_SUB_CLAUSE_PATTERN = re.compile(
    r"^(?:第.+款|[（(][一二三四五六七八九十0-9]+[）)])"
)


def normalize_regulation_anchor(value: str) -> str:
    """中文：移除法条锚点内部空格，生成稳定可检索编号。

    English: Remove internal anchor whitespace to create a stable searchable identifier.
    """

    return re.sub(r"\s+", "", value)


class RegulationChunkStrategy:
    """中文：在任何软语义算法之前为每一法条建立不可跨越的边界。

    English: Establish an uncrossable boundary for every article before soft semantic logic.
    """

    content_profile = ContentProfile.REGULATION

    def __init__(
        self,
        *,
        strategy_id: str,
        version: str,
        min_tokens: int,
        target_tokens: int,
        max_tokens: int,
        semantic_threshold: float = 0.52,
        ambiguity_margin: float = 0.08,
        similarity_provider: SimilarityProvider | None = None,
        llm_judge: LLMBoundaryJudge | None = None,
        create_parent_chunks: bool = True,
        max_llm_boundaries: int = 8,
        base_boundary_threshold: float = 0.58,
        boundary_weights: BoundaryWeights | None = None,
    ) -> None:
        """中文：保存法规策略身份并构造受法条键约束的通用切块核心。

        English: Store strategy identity and construct the article-key-constrained core chunker.
        """

        self.strategy_id = strategy_id
        self.version = version
        # 中文：关键变量 `boundary_analyzer` 仍负责条内的长度与语义边界选择。
        # English: Key variable `boundary_analyzer` still selects length/semantic splits
        # within an article.
        boundary_analyzer = AdaptiveBoundaryAnalyzer(
            min_tokens=min_tokens,
            target_tokens=target_tokens,
            max_tokens=max_tokens,
            hard_boundary_kinds=frozenset({"heading", "numbered_clause"}),
            semantic_threshold=semantic_threshold,
            ambiguity_margin=ambiguity_margin,
            similarity_provider=similarity_provider,
            llm_judge=llm_judge,
            base_boundary_threshold=base_boundary_threshold,
            boundary_weights=boundary_weights,
        )
        self._chunker = DynamicSemanticChunker(
            min_tokens=min_tokens,
            target_tokens=target_tokens,
            max_tokens=max_tokens,
            chunker_version=version,
            semantic_threshold=semantic_threshold,
            hard_boundary_kinds=frozenset({"heading", "numbered_clause"}),
            boundary_analyzer=boundary_analyzer,
            create_parent_chunks=create_parent_chunks,
            max_llm_boundaries=max_llm_boundaries,
        )

    def chunk(
        self,
        units: tuple[StructuredUnit, ...],
        context: ChunkingContext,
    ) -> tuple[Chunk, ...]:
        """中文：标注法规单元后生成法条内可分、法条间不可合并的 Chunk。

        English: Profile regulation units and allow splitting within, never merging across,
        articles.
        """

        strategy_context = ChunkingContext(
            tenant_id=context.tenant_id,
            source_id=context.source_id,
            document_id=context.document_id,
            document_version_id=context.document_version_id,
            content_profile=self.content_profile.value,
            strategy_id=self.strategy_id,
        )
        return self._chunker.chunk(self._profile_units(units), strategy_context)

    @staticmethod
    def _profile_units(units: tuple[StructuredUnit, ...]) -> tuple[StructuredUnit, ...]:
        """中文：顺序继承当前法条键，并保持正文只出现一次。

        English: Inherit the current article key sequentially while keeping body text unique.
        """

        # 中文：关键变量 `active_article_key` 从法条起始持续到下一法条或新章节。
        # English: Key variable `active_article_key` persists until the next article or heading.
        active_article_key: str | None = None
        # 中文：变量 `active_heading_path` 保存最近的法规编章节层级。
        # English: Variable `active_heading_path` stores the latest regulation heading hierarchy.
        active_heading_path: tuple[str, ...] = ()
        profiled: list[StructuredUnit] = []
        for unit in units:
            stripped = unit.text.strip()
            article_match = _ARTICLE_PATTERN.search(stripped)
            heading_match = _HEADING_PATTERN.search(stripped)
            kind = unit.kind
            section_number = unit.section_number
            protected = unit.protected
            if heading_match is not None:
                kind = "heading"
                protected = True
                active_article_key = None
                compact_heading = stripped.replace("\n", " ")[:160]
                active_heading_path = unit.heading_path or (compact_heading,)
            elif article_match is not None:
                kind = "numbered_clause"
                protected = True
                section_number = normalize_regulation_anchor(article_match.group(0))
                active_article_key = f"article:{section_number}"
            elif _SUB_CLAUSE_PATTERN.search(stripped) is not None:
                kind = "sub_clause"
            heading_path = active_heading_path or unit.heading_path
            profiled.append(
                StructuredUnit(
                    text=unit.text,
                    kind=kind,
                    heading_path=heading_path,
                    page_number=unit.page_number,
                    token_count=unit.token_count,
                    protected=protected,
                    section_number=section_number,
                    # 中文：法规检索正文不再为每个句子重复注入标题前缀。
                    # English: Regulation retrieval bodies no longer repeat headings per sentence.
                    retrieval_text=unit.text,
                    source_start_offset=unit.source_start_offset,
                    source_end_offset=unit.source_end_offset,
                    hard_boundary_key=active_article_key or unit.hard_boundary_key,
                )
            )
        return tuple(profiled)
