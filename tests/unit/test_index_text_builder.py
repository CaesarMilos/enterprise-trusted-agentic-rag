"""中文：验证 Dense 与 BM25 索引文本隔离并消除重复法规前缀。

English: Verify Dense/BM25 text isolation and removal of repeated regulation prefixes.
"""

from __future__ import annotations

from enterprise_rag.domain.models import Chunk
from enterprise_rag.indexing.index_text_builder import IndexTextBuilder


def _regulation_chunk(text: str) -> Chunk:
    """中文：构造包含旧式污染检索文本的法规 Chunk。

    English: Build a regulation chunk containing polluted legacy retrieval text.
    """

    return Chunk(
        id="chunk-a",
        tenant_id="tenant-a",
        source_id="source-a",
        document_id="document-a",
        document_version_id="version-a",
        ordinal=0,
        text=text,
        token_count=len(text),
        page_start=1,
        page_end=1,
        heading_path=("第二章 自然人", "第一节 民事权利能力和民事行为能力"),
        previous_chunk_id=None,
        next_chunk_id=None,
        boundary_reason="hard_boundary_key_change",
        chunker_version="regulation-structure-v5",
        content_hash="hash-a",
        retrieval_text=f"第二章 自然人\n第二章 自然人\n{text}\n{text}",
        section_number="第十三条",
        hard_boundary_key="article:第十三条",
    )


def test_index_text_uses_citable_body_instead_of_legacy_retrieval_prefix() -> None:
    """中文：索引文本必须从正文重建，不能继承旧 retrieval_text 的重复内容。

    English: Rebuild index text from body instead of inheriting repeated legacy retrieval text.
    """

    body = "第十三条 自然人从出生时起到死亡时止，具有民事权利能力。"
    payload = IndexTextBuilder().build(_regulation_chunk(body))

    assert payload.embedding_text.count(body) == 1
    assert payload.lexical_text.count(body) == 1
    assert payload.lexical_text.count("第二章 自然人") == 1


def test_embedding_text_is_bounded_and_preserves_head_and_tail() -> None:
    """中文：超长正文的 Dense 文本保留首尾且不超过配置词元数量级。

    English: Dense text for long bodies preserves head/tail within the configured token scale.
    """

    body = "第十三条 " + "甲" * 300 + "终止条件"
    payload = IndexTextBuilder(embedding_max_tokens=64).build(_regulation_chunk(body))

    assert "第十三条" in payload.embedding_text
    assert "终止条件" in payload.embedding_text
    assert "omitted" in payload.embedding_text
