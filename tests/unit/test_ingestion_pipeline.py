"""中文：本模块负责实现“测试资料接入流水线”相关功能。

English: Verify deterministic Markdown ingestion and dynamic structure-aware chunking.
"""

from __future__ import annotations

from pathlib import Path

from enterprise_rag.ingestion.chunk_strategies import build_default_strategy_registry
from enterprise_rag.ingestion.cleaner import TextCleaner
from enterprise_rag.ingestion.loader_registry import LoaderRegistry
from enterprise_rag.ingestion.loaders.markdown_loader import MarkdownLoader
from enterprise_rag.ingestion.metadata_extractor import MetadataExtractor
from enterprise_rag.ingestion.pipeline import IngestionPipeline
from enterprise_rag.ingestion.quality_validator import ChunkQualityValidator
from enterprise_rag.ingestion.semantic_chunker import ChunkingContext
from enterprise_rag.ingestion.structure_parser import StructureParser


def _pipeline() -> IngestionPipeline:
    """中文：该内部函数负责“流水线”相关处理。

    English: Construct a small deterministic pipeline for unit tests.
    """

    return IngestionPipeline(
        loaders=LoaderRegistry((MarkdownLoader(),)),
        cleaner=TextCleaner(),
        structure_parser=StructureParser(),
        strategy_registry=build_default_strategy_registry(5, 12, 24),
        metadata_extractor=MetadataExtractor(),
        quality_validator=ChunkQualityValidator(),
    )


def test_pipeline_is_deterministic_and_preserves_adjacency(tmp_path: Path) -> None:
    """中文：该测试用于验证“流水线为确定性并且`preserves`邻接关系”相关行为。

    English: Ensure repeated preparation produces identical chunks and valid neighbor links.
    """

    # 中文：变量 `document_path` 用于保存“文档`path`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Markdown fixture contains heading and topical boundaries.
    document_path = tmp_path / "policy.md"
    document_path.write_text(
        "# Leave Policy\n\n"
        "Employees receive annual leave. Leave requests require manager approval.\n\n"
        "## Security\n\n"
        "Passwords must never be shared. Security incidents must be reported promptly.",
        encoding="utf-8",
    )
    # 中文：变量 `context` 用于保存“上下文”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable domain identity is shared by both pipeline executions.
    context = ChunkingContext(
        tenant_id="tenant-a",
        source_id="source-a",
        document_id="document-a",
        document_version_id="version-a",
    )

    first = _pipeline().prepare(document_path, "policy.md", "md", context)
    second = _pipeline().prepare(document_path, "policy.md", "md", context)

    assert first.chunks == second.chunks
    assert first.metadata.title == "Leave Policy"
    assert len(first.chunks) >= 2
    for ordinal, chunk in enumerate(first.chunks):
        assert chunk.ordinal == ordinal
    # 中文：关键变量 `leaves` 单独验证源文邻接；父块不属于线性引用导航链。
    # English: Key variable `leaves` validates source adjacency; parents are outside that chain.
    leaves = tuple(chunk for chunk in first.chunks if chunk.chunk_level == "leaf")
    for leaf_index, chunk in enumerate(leaves):
        if leaf_index > 0:
            assert chunk.previous_chunk_id == leaves[leaf_index - 1].id
        if leaf_index + 1 < len(leaves):
            assert chunk.next_chunk_id == leaves[leaf_index + 1].id


def test_chunker_respects_hard_token_maximum(tmp_path: Path) -> None:
    """中文：该测试用于验证“切块器遵守硬性词元最大值”相关行为。

    English: Ensure an oversized single paragraph is deterministically split.
    """

    # 中文：变量 `document_path` 用于保存“文档`path`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Repeated terms create a unit much larger than the configured maximum.
    document_path = tmp_path / "long.md"
    document_path.write_text("# Long\n\n" + "evidence " * 100, encoding="utf-8")
    # 中文：变量 `context` 用于保存“上下文”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable identity context allows deterministic chunk IDs.
    context = ChunkingContext("tenant-a", "source-a", "document-a", "version-a")

    prepared = _pipeline().prepare(document_path, "long.md", "md", context)

    assert prepared.chunks
    assert all(chunk.token_count <= 24 for chunk in prepared.chunks)


def test_pipeline_rejects_frozen_parameter_drift(tmp_path: Path) -> None:
    """中文：确认排队任务的冻结切块参数与当前 Worker 不一致时明确失败。

    English: Ensure a queued job fails explicitly when frozen chunk parameters differ from the
    current worker.
    """

    document_path = tmp_path / "drift.md"
    document_path.write_text("# 标题\n\n稳定的说明正文。", encoding="utf-8")
    pipeline = IngestionPipeline(
        loaders=LoaderRegistry((MarkdownLoader(),)),
        cleaner=TextCleaner(),
        structure_parser=StructureParser(),
        strategy_registry=build_default_strategy_registry(5, 12, 24),
        metadata_extractor=MetadataExtractor(),
        quality_validator=ChunkQualityValidator(),
        runtime_chunk_parameters={"target_tokens": 12},
    )

    try:
        pipeline.prepare(
            document_path,
            "drift.md",
            "md",
            ChunkingContext("tenant-a", "source-a", "document-a", "version-a"),
            expected_chunk_parameters={"target_tokens": 99},
        )
    except ValueError as exc:
        assert "frozen chunk parameters" in str(exc)
    else:
        raise AssertionError("parameter drift must not be accepted")
