"""中文：本模块负责实现“流水线”相关功能。

English: Orchestrate validation-neutral loading, cleaning, structure recovery, and chunking.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from enterprise_rag.core.enums import ContentProfile
from enterprise_rag.domain.models import Chunk
from enterprise_rag.ingestion.chunk_strategies import ChunkStrategyRegistry
from enterprise_rag.ingestion.cleaner import CleaningStats, TextCleaner
from enterprise_rag.ingestion.loader_registry import LoaderRegistry
from enterprise_rag.ingestion.metadata_extractor import ExtractedMetadata, MetadataExtractor
from enterprise_rag.ingestion.quality_validator import ChunkQualityValidator, QualityAssessment
from enterprise_rag.ingestion.semantic_chunker import ChunkingContext
from enterprise_rag.ingestion.structure_parser import StructureParser


@dataclass(frozen=True, slots=True)
class PreparedDocument:
    """中文：该类用于表示或实现“已准备的文档（PreparedDocument）”的职责。

    English: Represent immutable ingestion output consumed by persistence and indexing.
    """

    # 中文：变量 `chunks` 用于保存“文本块”相关数据；其精确定义与约束见下方英文说明。
    # English: Ordered deterministic chunks.
    chunks: tuple[Chunk, ...]
    # 中文：变量 `metadata` 用于保存“元数据”相关数据；其精确定义与约束见下方英文说明。
    # English: Safe derived document metadata.
    metadata: ExtractedMetadata
    # 中文：变量 `cleaning_stats` 用于保存“`cleaning``stats`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Cleaning measurements retained for trace output.
    cleaning_stats: CleaningStats
    # 中文：接入质量指标用于审计、管理展示和策略回归测试。
    # English: Ingestion quality metrics support audit, administration, and regression tests.
    quality_assessment: QualityAssessment


class IngestionPipeline:
    """中文：该类用于表示或实现“资料接入流水线（IngestionPipeline）”的职责。

    English: Run every deterministic content-preparation stage in a fixed order.
    """

    def __init__(
        self,
        loaders: LoaderRegistry,
        cleaner: TextCleaner,
        structure_parser: StructureParser,
        strategy_registry: ChunkStrategyRegistry,
        metadata_extractor: MetadataExtractor,
        quality_validator: ChunkQualityValidator,
        runtime_chunk_parameters: dict[str, object] | None = None,
        runtime_embedding_fingerprint: str = "",
        runtime_boundary_model_fingerprint: str | None = None,
    ) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store stateless pipeline components for repeated worker use.
        """

        # 中文：变量 `_loaders` 用于保存“`loaders`”相关数据；其精确定义与约束见下方英文说明。
        # English: Registry selects a parser only from a verified media type.
        self._loaders = loaders
        # 中文：变量 `_cleaner` 用于保存“清洗器”相关数据；其精确定义与约束见下方英文说明。
        # English: Cleaner creates stable normalized text.
        self._cleaner = cleaner
        # 中文：变量 `_structure_parser` 用于保存“`structure`解析器”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Structure parser restores headings, pages, and sentence units.
        self._structure_parser = structure_parser
        # 中文：变量 `_strategy_registry` 根据资料源画像解析唯一切块策略。
        # English: Strategy registry resolves one chunk strategy from the source profile.
        self._strategy_registry = strategy_registry
        # 中文：变量 `_metadata_extractor` 用于保存“元数据`extractor`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Metadata extractor creates safe routing and administration values.
        self._metadata_extractor = metadata_extractor
        # 中文：变量 `_quality_validator` 在持久化前阻止明显无效的切块结果。
        # English: Quality validator blocks clearly unsafe chunk output before persistence.
        self._quality_validator = quality_validator
        # 中文：以下运行时指纹用于验证排队任务的冻结快照，禁止静默配置漂移。
        # English: Runtime fingerprints validate queued-job snapshots and prevent silent drift.
        self._runtime_chunk_parameters = dict(runtime_chunk_parameters or {})
        self._runtime_embedding_fingerprint = runtime_embedding_fingerprint
        self._runtime_boundary_model_fingerprint = runtime_boundary_model_fingerprint

    def prepare(
        self,
        path: Path,
        filename: str,
        media_type: str,
        context: ChunkingContext,
        content_profile: ContentProfile = ContentProfile.GENERAL_PROSE,
        strategy_override: str | None = None,
        expected_strategy_version: str | None = None,
        expected_chunk_parameters: dict[str, object] | None = None,
        expected_embedding_fingerprint: str = "",
        expected_boundary_model_fingerprint: str | None = None,
    ) -> PreparedDocument:
        """中文：该函数或方法负责“准备”相关处理。

        English: Produce immutable deterministic chunks from one validated local document.
        """

        # 中文：变量 `loaded` 用于保存“`loaded`”相关数据；其精确定义与约束见下方英文说明。
        # English: Loader output preserves format-specific source order.
        loaded = self._loaders.get(media_type).load(path, filename, media_type)
        # 中文：变量 `cleaned` 用于保存“`cleaned`”相关数据；其精确定义与约束见下方英文说明。
        # English: Cleaned copy supplies stable text for IDs and retrieval.
        cleaned = self._cleaner.clean(loaded)
        # 中文：变量 `units` 用于保存“`units`”相关数据；其精确定义与约束见下方英文说明。
        # English: Structured units expose headings and semantic boundary candidates.
        units = self._structure_parser.parse(cleaned)
        # 中文：变量 `chunks` 用于保存“文本块”相关数据；其精确定义与约束见下方英文说明。
        # English: Chunks include stable IDs, source positions, and adjacency.
        # 中文：变量 `strategy` 是管理员画像解析后的确定性切块实现。
        # English: Strategy is the deterministic chunk implementation resolved by profile.
        strategy = self._strategy_registry.resolve(content_profile, strategy_override)
        if expected_strategy_version is not None and strategy.version != expected_strategy_version:
            raise ValueError(
                "frozen chunk strategy version is unavailable: "
                f"expected {expected_strategy_version}, resolved {strategy.version}"
            )
        if (
            expected_chunk_parameters
            and expected_chunk_parameters != self._runtime_chunk_parameters
        ):
            raise ValueError("frozen chunk parameters differ from the active worker configuration")
        if (
            expected_embedding_fingerprint
            and expected_embedding_fingerprint != self._runtime_embedding_fingerprint
        ):
            raise ValueError("frozen embedding fingerprint differs from the active worker model")
        if (
            expected_boundary_model_fingerprint is not None
            and expected_boundary_model_fingerprint
            != self._runtime_boundary_model_fingerprint
        ):
            raise ValueError("frozen boundary model differs from the active worker model")
        chunks = strategy.chunk(units, context)
        quality_assessment = self._quality_validator.validate(
            cleaned,
            chunks,
            content_profile,
        )
        # 中文：变量 `metadata` 用于保存“元数据”相关数据；其精确定义与约束见下方英文说明。
        # English: Derived metadata is created only after final chunks are frozen.
        metadata = self._metadata_extractor.extract(filename, media_type, chunks)
        return PreparedDocument(
            chunks=chunks,
            metadata=metadata,
            cleaning_stats=cleaned.stats,
            quality_assessment=quality_assessment,
        )
