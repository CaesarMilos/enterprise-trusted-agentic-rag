"""中文：验证法规切分始终保留法条硬边界与唯一检索正文。

English: Verify regulation chunking preserves article hard boundaries and unique bodies.
"""

from __future__ import annotations

from enterprise_rag.core.enums import ContentProfile
from enterprise_rag.ingestion.chunk_strategies import build_default_strategy_registry
from enterprise_rag.ingestion.semantic_chunker import ChunkingContext
from enterprise_rag.ingestion.structure_parser import StructuredUnit, estimate_tokens


def _unit(text: str, ordinal: int) -> StructuredUnit:
    """中文：构造带稳定源码范围的法规结构单元。

    English: Build one regulation unit with a stable source range.
    """

    # 中文：关键变量 `start` 模拟规范文档中的单调字符坐标。
    # English: Key variable `start` simulates a monotonic normalized-document offset.
    start = ordinal * 200
    return StructuredUnit(
        text=text,
        kind="paragraph",
        heading_path=("第二章 自然人", "第一节 民事权利能力和民事行为能力"),
        page_number=1,
        token_count=estimate_tokens(text),
        source_start_offset=start,
        source_end_offset=start + len(text),
    )


def test_short_regulation_articles_never_merge_across_article_keys() -> None:
    """中文：即使法条短于最小长度，每个法条也必须保持独立叶子块。

    English: Keep every article as an independent leaf even below the soft minimum size.
    """

    strategy = build_default_strategy_registry(80, 120, 200).resolve(
        ContentProfile.REGULATION
    )
    units = (
        _unit("第十三条 自然人从出生时起到死亡时止，具有民事权利能力。", 0),
        _unit("第十四条 自然人的民事权利能力一律平等。", 1),
        _unit("第十五条 自然人的出生时间和死亡时间，以证明记载为准。", 2),
    )

    chunks = strategy.chunk(
        units,
        ChunkingContext("tenant-a", "source-a", "document-a", "version-a"),
    )
    leaves = tuple(chunk for chunk in chunks if chunk.chunk_level == "leaf")

    assert tuple(chunk.section_number for chunk in leaves) == (
        "第十三条",
        "第十四条",
        "第十五条",
    )
    assert tuple(chunk.hard_boundary_key for chunk in leaves) == (
        "article:第十三条",
        "article:第十四条",
        "article:第十五条",
    )
    assert all(chunk.retrieval_text.count(chunk.text) == 1 for chunk in leaves)
    assert all(chunk.retrieval_text.count("第二章 自然人") == 1 for chunk in leaves)
    assert all(chunk.text.count("条") == 1 for chunk in leaves)


def test_regulation_overlap_never_crosses_article_boundary() -> None:
    """中文：相邻法条不得把上一条句子复制到下一条检索文本。

    English: Never copy a previous article sentence into the next article retrieval text.
    """

    strategy = build_default_strategy_registry(1, 20, 45).resolve(ContentProfile.REGULATION)
    units = (
        _unit("第八条 民事主体从事民事活动，不得违反法律，不得违背公序良俗。", 0),
        _unit("第九条 民事主体从事民事活动，应当有利于节约资源、保护生态环境。", 1),
    )

    chunks = strategy.chunk(
        units,
        ChunkingContext("tenant-a", "source-a", "document-a", "version-a"),
    )
    leaves = tuple(chunk for chunk in chunks if chunk.chunk_level == "leaf")

    article_nine = next(chunk for chunk in leaves if chunk.section_number == "第九条")
    assert "第八条" not in article_nine.search_text
    assert article_nine.metadata["overlap_text"] == ""
