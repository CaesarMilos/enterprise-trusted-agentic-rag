"""中文：本模块负责实现“清洗器”相关功能。

English: Normalize extracted text deterministically while retaining cleaning statistics.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from enterprise_rag.ingestion.loaders.base import LoadedDocument, RawBlock
from enterprise_rag.ingestion.pdf_reflow import PDFReflowStats, PDFTextReflow

# 中文：变量 `_HORIZONTAL_WHITESPACE` 用于保存“`horizontal``whitespace`”相关数据；
# 其精确定义与约束见下方英文说明。
# English: Horizontal whitespace collapses while deliberate line breaks remain available.
_HORIZONTAL_WHITESPACE = re.compile(r"[^\S\n]+")
# 中文：变量 `_EXCESS_NEWLINES` 用于保存“`excess``newlines`”相关数据；
# 其精确定义与约束见下方英文说明。
# English: Three or more newlines are normalized to a paragraph break.
_EXCESS_NEWLINES = re.compile(r"\n{3,}")
# 中文：变量 `_CONTROL_CHARACTERS` 用于保存“`control``characters`”相关数据；
# 其精确定义与约束见下方英文说明。
# English: Most C0 control characters are unsafe and semantically meaningless in documents.
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass(frozen=True, slots=True)
class CleaningStats:
    """中文：该类用于表示或实现“清洗`stats`（CleaningStats）”的职责。

    English: Record deterministic text-cleaning effects for traces and debugging.
    """

    # 中文：变量 `original_characters` 用于保存“原始`characters`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Character count before normalization.
    original_characters: int
    # 中文：变量 `cleaned_characters` 用于保存“`cleaned``characters`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Character count after normalization and empty-block removal.
    cleaned_characters: int
    # 中文：变量 `removed_blocks` 用于保存“`removed``blocks`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Number of blocks removed because no text remained.
    removed_blocks: int
    # 中文：变量 `reflowed_lines` 记录PDF视觉断行恢复时合并的行数。
    # English: Number of visual PDF line wraps joined during reflow.
    reflowed_lines: int = 0
    # 中文：变量 `removed_margin_lines` 记录确定性删除的重复页眉页脚行数。
    # English: Number of repeated header or footer lines removed deterministically.
    removed_margin_lines: int = 0
    # 中文：变量 `repaired_markers` 记录恢复的孤立标点和列表编号数量。
    # English: Number of isolated punctuation or list markers repaired.
    repaired_markers: int = 0


@dataclass(frozen=True, slots=True)
class CleanedDocument:
    """中文：该类用于表示或实现“已清洗的文档（CleanedDocument）”的职责。

    English: Represent normalized blocks and safe cleaning statistics.
    """

    # 中文：变量 `filename` 用于保存“`filename`”相关数据；其精确定义与约束见下方英文说明。
    # English: Safe original display filename.
    filename: str
    # 中文：变量 `media_type` 用于保存“`media``type`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Verified lowercase document type.
    media_type: str
    # 中文：变量 `blocks` 用于保存“`blocks`”相关数据；其精确定义与约束见下方英文说明。
    # English: Ordered non-empty normalized blocks.
    blocks: tuple[RawBlock, ...]
    # 中文：变量 `metadata` 用于保存“元数据”相关数据；其精确定义与约束见下方英文说明。
    # English: Loader metadata copied without mutation.
    metadata: dict[str, object]
    # 中文：变量 `stats` 用于保存“`stats`”相关数据；其精确定义与约束见下方英文说明。
    # English: Aggregate normalization measurements.
    stats: CleaningStats


class TextCleaner:
    """中文：该类用于表示或实现“文本清洗器（TextCleaner）”的职责。

    English: Apply Unicode, whitespace, and control-character normalization.
    """

    def __init__(self, pdf_reflow: PDFTextReflow | None = None) -> None:
        """中文：保存可替换的PDF版式恢复器，便于测试和部署定制。

        English: Store a replaceable PDF reflow component for testing and deployment tuning.
        """

        # 中文：变量 `_pdf_reflow` 只处理PDF，TXT和Markdown继续保持原格式边界。
        # English: PDF reflow is applied only to PDFs; TXT and Markdown retain format boundaries.
        self._pdf_reflow = pdf_reflow or PDFTextReflow()

    def clean(self, document: LoadedDocument) -> CleanedDocument:
        """中文：该函数或方法负责“清洗”相关处理。

        English: Return a normalized copy without mutating loader output.
        """

        # 中文：变量 `original_characters` 用于保存“原始`characters`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Total input count supports traceable data-loss detection.
        original_characters = sum(len(block.text) for block in document.blocks)
        # 中文：变量 `source_blocks` 保存可选PDF版式恢复后的有序分页文本。
        # English: Source blocks contain optional PDF reflow output in physical page order.
        reflow_stats = PDFReflowStats(0, 0, 0, 0, 0)
        source_blocks = document.blocks
        if document.media_type == "pdf":
            reflowed = self._pdf_reflow.reflow(document.blocks)
            source_blocks = reflowed.blocks
            reflow_stats = reflowed.stats
        # 中文：变量 `cleaned_blocks` 用于保存“`cleaned``blocks`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Clean block collection preserves loader order.
        cleaned_blocks: list[RawBlock] = []
        # 中文：变量 `removed_blocks` 用于保存“`removed``blocks`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Removed block count explains a smaller output.
        removed_blocks = 0
        for block in source_blocks:
            # 中文：变量 `normalized` 用于保存“`normalized`”相关数据；
            # 其精确定义与约束见下方英文说明。
            # English: NFKC normalizes compatibility variants for stable chunk identity
            #   and search.
            normalized = unicodedata.normalize("NFKC", block.text)
            normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
            normalized = _CONTROL_CHARACTERS.sub("", normalized)
            normalized = _HORIZONTAL_WHITESPACE.sub(" ", normalized)
            normalized = _EXCESS_NEWLINES.sub("\n\n", normalized).strip()
            if not normalized:
                removed_blocks += 1
                continue
            cleaned_blocks.append(
                RawBlock(
                    text=normalized,
                    kind=block.kind,
                    page_number=block.page_number,
                    heading_level=block.heading_level,
                    metadata=dict(block.metadata),
                )
            )
        # 中文：变量 `cleaned_characters` 用于保存“`cleaned``characters`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Final character count verifies the effect of normalization.
        cleaned_characters = sum(len(block.text) for block in cleaned_blocks)
        return CleanedDocument(
            filename=document.filename,
            media_type=document.media_type,
            blocks=tuple(cleaned_blocks),
            metadata=dict(document.metadata),
            stats=CleaningStats(
                original_characters=original_characters,
                cleaned_characters=cleaned_characters,
                removed_blocks=removed_blocks,
                reflowed_lines=reflow_stats.joined_lines,
                removed_margin_lines=reflow_stats.removed_margin_lines,
                repaired_markers=reflow_stats.repaired_markers,
            ),
        )
