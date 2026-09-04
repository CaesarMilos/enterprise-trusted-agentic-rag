"""中文：本模块负责实现“PDF加载器”相关功能。

English: Load text-based PDF files page by page while preserving page locations.
"""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from enterprise_rag.core.enums import ErrorCategory
from enterprise_rag.core.exceptions import ParsingError, error_detail
from enterprise_rag.ingestion.loaders.base import LoadedDocument, RawBlock
from enterprise_rag.ingestion.ocr import OCRProvider


class PDFLoader:
    """中文：该类用于表示或实现“PDF加载器（PDFLoader）”的职责。

    English: Extract text PDFs and classify scanned or hybrid documents for OCR routing.
    """

    def __init__(
        self,
        ocr_provider: OCRProvider | None = None,
        minimum_ocr_confidence: float = 0.75,
    ) -> None:
        """中文：保存可选 OCR 适配器与进入索引所需的最低识别置信度。

        English: Store an optional OCR adapter and minimum confidence required for indexing.
        """

        if not 0.0 <= minimum_ocr_confidence <= 1.0:
            raise ValueError("minimum OCR confidence must be between zero and one")
        # 中文：变量 `_ocr_provider` 允许接入本地或远程 OCR，不绑定具体 SDK。
        # English: OCR provider supports local or remote adapters without binding an SDK.
        self._ocr_provider = ocr_provider
        # 中文：低置信度 OCR 输出必须人工复核，避免错误文字静默建索引。
        # English: Low-confidence OCR output requires review before indexing.
        self._minimum_ocr_confidence = minimum_ocr_confidence

    @property
    def media_types(self) -> frozenset[str]:
        """中文：该函数或方法负责“媒体类型”相关处理。

        English: Return the PDF type supported by this loader.
        """

        return frozenset({"pdf"})

    def load(self, path: Path, filename: str, media_type: str) -> LoadedDocument:
        """中文：该函数或方法负责“加载并解析目标数据”相关处理。

        English: Extract non-empty page text in physical page order.
        """

        try:
            # 中文：变量 `reader` 用于保存“`reader`”相关数据；其精确定义与约束见下方英文说明。
            # English: Reader parses only validated local bytes and never follows external
            #   links.
            reader = PdfReader(path)
            if reader.is_encrypted:
                raise ParsingError(
                    error_detail(
                        "PDF_UNSUPPORTED",
                        ErrorCategory.PARSING,
                        "Encrypted PDF documents are not supported.",
                    )
                )
            # 中文：变量 `blocks` 用于保存“`blocks`”相关数据；其精确定义与约束见下方英文说明。
            # English: Page blocks preserve one-based locations for citations.
            blocks = tuple(
                RawBlock(
                    text=page.extract_text() or "",
                    kind="page",
                    page_number=page_number,
                )
                for page_number, page in enumerate(reader.pages, start=1)
            )
        except ParsingError:
            raise
        except Exception as exc:
            raise ParsingError(
                error_detail(
                    "PDF_PARSE_FAILED",
                    ErrorCategory.PARSING,
                    "The PDF document could not be parsed.",
                )
            ) from exc
        # 中文：变量 `extracted_characters` 用于保存“`extracted``characters`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Total extracted character count differentiates empty/scanned PDFs from
        #   short pages.
        extracted_characters = sum(len(block.text.strip()) for block in blocks)
        # 中文：变量 `text_page_count` 统计具有有效文本层的页面数量。
        # English: Text page count measures pages with a usable text layer.
        text_page_count = sum(1 for block in blocks if len(block.text.strip()) >= 5)
        # 中文：变量 `text_coverage_ratio` 用于区分文本型、混合型与扫描型 PDF。
        # English: Text coverage distinguishes native, hybrid, and scanned PDFs.
        text_coverage_ratio = text_page_count / len(blocks) if blocks else 0.0
        pdf_kind = (
            "text_pdf"
            if text_coverage_ratio >= 0.9
            else "hybrid_pdf"
            if text_coverage_ratio > 0
            else "scanned_pdf"
        )
        # 中文：关键变量 `missing_pages` 精确列出缺少可用文本层的物理页。
        # English: Key variable `missing_pages` identifies every physical page lacking usable text.
        missing_pages = tuple(block.page_number for block in blocks if len(block.text.strip()) < 5)
        if not blocks or missing_pages:
            if self._ocr_provider is not None:
                # 中文：变量 `ocr_result` 包含按页排序文字、置信度与提供方版本。
                # English: OCR result contains page-ordered text, confidence, and version.
                try:
                    ocr_result = self._ocr_provider.extract_pdf(path)
                except Exception as exc:
                    raise ParsingError(
                        error_detail(
                            "PDF_OCR_REQUIRED",
                            ErrorCategory.PARSING,
                            "The configured OCR provider could not process this PDF.",
                            ocr_provider_error=type(exc).__name__,
                        )
                    ) from exc
                if not ocr_result.blocks or (
                    ocr_result.mean_confidence < self._minimum_ocr_confidence
                ):
                    raise ParsingError(
                        error_detail(
                            "DOCUMENT_NEEDS_REVIEW",
                            ErrorCategory.PARSING,
                            "OCR output confidence is too low for automatic indexing.",
                            ocr_provider_version=ocr_result.provider_version,
                            ocr_mean_confidence=f"{ocr_result.mean_confidence:.4f}",
                        )
                    )
                # 中文：只用 OCR 补齐缺页，已有高质量原生文本层继续保留。
                # English: OCR fills only missing pages while usable native text remains intact.
                ocr_by_page = {
                    block.page_number: block
                    for block in ocr_result.blocks
                    if block.page_number is not None and block.text.strip()
                }
                unresolved_pages = tuple(
                    page_number for page_number in missing_pages if page_number not in ocr_by_page
                )
                if unresolved_pages:
                    raise ParsingError(
                        error_detail(
                            "DOCUMENT_NEEDS_REVIEW",
                            ErrorCategory.PARSING,
                            "OCR did not return text for every missing PDF page.",
                            missing_pages=",".join(str(page) for page in unresolved_pages),
                        )
                    )
                merged_blocks = tuple(
                    ocr_by_page[block.page_number]
                    if block.page_number is not None and block.page_number in missing_pages
                    else block
                    for block in blocks
                )
                ocr_characters = sum(len(block.text.strip()) for block in merged_blocks)
                return LoadedDocument(
                    filename=filename,
                    media_type=media_type,
                    blocks=merged_blocks,
                    metadata={
                        "page_count": len(blocks),
                        "text_page_count": text_page_count,
                        "text_coverage_ratio": round(text_coverage_ratio, 4),
                        "pdf_kind": pdf_kind,
                        "extracted_characters": ocr_characters,
                        "ocr_applied": True,
                        "ocr_provider_version": ocr_result.provider_version,
                        "ocr_mean_confidence": round(ocr_result.mean_confidence, 4),
                        "ocr_page_numbers": list(missing_pages),
                    },
                )
            raise ParsingError(
                error_detail(
                    "PDF_OCR_REQUIRED",
                    ErrorCategory.PARSING,
                    "Every PDF page must have native text or OCR text before indexing.",
                    pdf_kind=pdf_kind,
                    text_coverage_ratio=f"{text_coverage_ratio:.4f}",
                    missing_pages=",".join(str(page) for page in missing_pages),
                )
            )
        return LoadedDocument(
            filename=filename,
            media_type=media_type,
            blocks=tuple(block for block in blocks if block.text.strip()),
            metadata={
                "page_count": len(blocks),
                "text_page_count": text_page_count,
                "text_coverage_ratio": round(text_coverage_ratio, 4),
                "pdf_kind": pdf_kind,
                "extracted_characters": extracted_characters,
            },
        )
