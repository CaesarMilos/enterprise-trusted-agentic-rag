"""中文：本模块定义扫描与混合 PDF 可插拔 OCR 能力的稳定领域边界。

English: Define the stable pluggable OCR boundary for scanned and hybrid PDF documents.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from enterprise_rag.ingestion.loaders.base import RawBlock


@dataclass(frozen=True, slots=True)
class OCRResult:
    """中文：保存 OCR 提取的有序页面块、置信度与提供方版本。

    English: Store ordered OCR page blocks, confidence, and provider version metadata.
    """

    # 中文：OCR 页面块保持原始页码，供引用与后续版面分析使用。
    # English: OCR page blocks preserve page numbers for citations and layout analysis.
    blocks: tuple[RawBlock, ...]
    # 中文：平均置信度用于决定 READY 或 NEEDS_REVIEW。
    # English: Mean confidence supports READY versus NEEDS_REVIEW decisions.
    mean_confidence: float
    # 中文：提供方版本参与处理审计和回归评估。
    # English: Provider version participates in processing audit and regression evaluation.
    provider_version: str


class OCRProvider(Protocol):
    """中文：约束本地或远程 OCR 适配器必须实现的统一接口。

    English: Define the common interface required from local or remote OCR adapters.
    """

    def extract_pdf(self, path: Path) -> OCRResult:
        """中文：从受信任本地 PDF 路径提取按页排序的文字块。

        English: Extract page-ordered text blocks from a trusted local PDF path.
        """
