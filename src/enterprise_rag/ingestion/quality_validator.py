"""中文：本模块评估清洗与切块结果，阻止明显低质量内容静默进入索引。

English: Assess cleaning/chunk output and prevent clearly unsafe content entering indexes.
"""

from __future__ import annotations

from dataclasses import dataclass

from enterprise_rag.core.enums import ContentProfile, ErrorCategory
from enterprise_rag.core.exceptions import ChunkValidationError, ParsingError, error_detail
from enterprise_rag.domain.models import Chunk
from enterprise_rag.ingestion.cleaner import CleanedDocument


@dataclass(frozen=True, slots=True)
class QualityAssessment:
    """中文：保存可审计的接入质量指标与非阻断警告。

    English: Store auditable ingestion quality metrics and non-blocking warnings.
    """

    # 中文：质量门是否允许内容进入持久化和索引阶段。
    # English: Whether the quality gate allows persistence and indexing.
    passed: bool
    # 中文：稳定指标用于管理页面、测试和后续阈值调优。
    # English: Stable metrics support administration, testing, and threshold tuning.
    metrics: dict[str, float | int | str]
    # 中文：警告不阻断接入，但提示目录污染或碎片化等风险。
    # English: Warnings do not block ingestion but expose TOC or fragmentation risks.
    warnings: tuple[str, ...] = ()


class ChunkQualityValidator:
    """中文：对目标技术资料执行保守、确定性的切块质量检查。

    English: Apply conservative deterministic chunk-quality checks to target technical content.
    """

    def __init__(self, max_chunk_tokens: int = 700) -> None:
        """中文：保存发布允许的叶子块硬 Token 上限。

        English: Store the hard leaf-token maximum permitted by the publication gate.
        """

        if max_chunk_tokens < 1:
            raise ValueError("max_chunk_tokens must be positive")
        self._max_chunk_tokens = max_chunk_tokens

    def validate(
        self,
        cleaned: CleanedDocument,
        chunks: tuple[Chunk, ...],
        content_profile: ContentProfile,
    ) -> QualityAssessment:
        """中文：返回质量评估，并对无有效文本或完全碎片化结果要求人工复核。

        English: Return an assessment and require review for empty or fully fragmented output.
        """

        # 中文：变量 `cleaned_characters` 表示真正参与结构解析的非空字符量。
        # English: Cleaned characters measure usable text entering structure parsing.
        cleaned_characters = cleaned.stats.cleaned_characters
        if cleaned_characters <= 0 or not chunks:
            raise ParsingError(
                error_detail(
                    "DOCUMENT_NEEDS_REVIEW",
                    ErrorCategory.PARSING,
                    "No usable chunks were produced from the extracted document text.",
                )
            )
        # 中文：质量计算只统计叶子块，避免父上下文块重复扭曲碎片率。
        # English: Quality metrics use leaves only so parent context does not distort ratios.
        leaf_chunks = tuple(chunk for chunk in chunks if chunk.chunk_level == "leaf") or chunks
        parent_chunks = tuple(chunk for chunk in chunks if chunk.chunk_level == "parent")
        if any(not chunk.text.strip() for chunk in chunks):
            self._fail("empty_chunk", "The chunk set contains empty text.")
        if any(chunk.token_count > self._max_chunk_tokens for chunk in leaf_chunks):
            self._fail("oversized_chunk", "A leaf chunk exceeds the configured hard token limit.")
        if any(
            chunk.page_start is not None
            and chunk.page_end is not None
            and chunk.page_start > chunk.page_end
            for chunk in chunks
        ):
            self._fail("inverted_page_range", "A chunk has an inverted page range.")
        # 中文：所有 Parent 引用必须双向闭合，防止扩展阶段加载不存在或错误归属的上下文。
        # English: Parent references must close bidirectionally to prevent invalid expansion.
        parent_by_id = {chunk.id: chunk for chunk in parent_chunks}
        chunk_by_id = {chunk.id: chunk for chunk in chunks}
        if len(chunk_by_id) != len(chunks):
            self._fail("duplicate_chunk_id", "The chunk set contains duplicate identifiers.")
        for leaf in leaf_chunks:
            if leaf.parent_chunk_id is not None and leaf.parent_chunk_id not in parent_by_id:
                self._fail("missing_parent", "A leaf chunk references a missing parent chunk.")
        for parent in parent_chunks:
            child_ids = parent.metadata.get("child_chunk_ids", [])
            if not isinstance(child_ids, list) or any(
                child_id not in chunk_by_id or chunk_by_id[child_id].parent_chunk_id != parent.id
                for child_id in child_ids
            ):
                self._fail("broken_parent_child", "A parent-child relation is not reciprocal.")
        tiny_chunk_count = sum(1 for chunk in leaf_chunks if chunk.token_count < 20)
        tiny_ratio = tiny_chunk_count / len(leaf_chunks)
        warnings: list[str] = []
        if len(leaf_chunks) >= 5 and tiny_ratio >= 0.8:
            warnings.append("high_fragmentation_ratio")
        if len(leaf_chunks) >= 10 and tiny_ratio >= 0.95:
            raise ParsingError(
                error_detail(
                    "DOCUMENT_NEEDS_REVIEW",
                    ErrorCategory.PARSING,
                    "Chunk output is almost entirely fragmented and requires review.",
                    tiny_chunk_ratio=f"{tiny_ratio:.4f}",
                )
            )
        duplicate_ratio = 1.0 - len({chunk.content_hash for chunk in leaf_chunks}) / len(
            leaf_chunks
        )
        if len(leaf_chunks) >= 5 and duplicate_ratio >= 0.5:
            warnings.append("high_duplicate_content_ratio")
        if len(leaf_chunks) >= 10 and duplicate_ratio >= 0.8:
            self._fail(
                "duplicate_content",
                "The chunk set contains an unsafe amount of duplicate content.",
            )
        # 中文：目录标记只产生警告，避免对正常带目录说明书进行误拒绝。
        # English: TOC markers warn without rejecting legitimate manuals containing contents.
        first_text = "\n".join(chunk.text for chunk in leaf_chunks[:3])
        if "目录" in first_text or "table of contents" in first_text.lower():
            warnings.append("possible_table_of_contents")
        expected_structures = {
            ContentProfile.MANUAL: {"heading", "step", "warning", "parameter", "troubleshooting"},
            ContentProfile.TECHNICAL_DOC: {
                "heading",
                "api_section",
                "config",
                "parameter",
                "warning",
            },
            ContentProfile.REGULATION: {"heading", "numbered_clause", "sub_clause"},
            ContentProfile.ACADEMIC: {"heading", "citation_list"},
            ContentProfile.NARRATIVE: {"heading", "scene_break"},
        }
        expected = expected_structures.get(content_profile, set())
        structural_chunk_count = sum(chunk.unit_type in expected for chunk in leaf_chunks)
        if expected and structural_chunk_count == 0:
            warnings.append("content_profile_signal_weak")
        metrics: dict[str, float | int | str] = {
            "content_profile": content_profile.value,
            "cleaned_characters": cleaned_characters,
            "chunk_count": len(chunks),
            "leaf_chunk_count": len(leaf_chunks),
            "parent_chunk_count": len(chunks) - len(leaf_chunks),
            "tiny_chunk_count": tiny_chunk_count,
            "tiny_chunk_ratio": round(tiny_ratio, 4),
            "duplicate_content_ratio": round(duplicate_ratio, 4),
            "average_chunk_tokens": round(
                sum(chunk.token_count for chunk in leaf_chunks) / len(leaf_chunks), 2
            ),
            "reflowed_lines": cleaned.stats.reflowed_lines,
            "removed_margin_lines": cleaned.stats.removed_margin_lines,
            "repaired_markers": cleaned.stats.repaired_markers,
            "profile_structural_chunk_count": structural_chunk_count,
        }
        return QualityAssessment(True, metrics, tuple(warnings))

    @staticmethod
    def _fail(reason: str, message: str) -> None:
        """中文：把严重质量问题统一转换为阻断发布的稳定错误码。

        English: Convert a severe quality issue into one stable publication-blocking code.
        """

        raise ChunkValidationError(
            error_detail(
                "CHUNK_VALIDATION_FAILED",
                ErrorCategory.PARSING,
                message,
                reason=reason,
            )
        )
