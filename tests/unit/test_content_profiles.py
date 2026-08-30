"""中文：验证资料源内容画像、专用切块策略和 PDF OCR 分流行为。

English: Verify source profiles, specialized chunk strategies, and PDF OCR routing behavior.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pypdf import PdfWriter

import enterprise_rag.ingestion.loaders.pdf_loader as pdf_loader_module
from enterprise_rag.core.enums import ContentProfile
from enterprise_rag.core.exceptions import ParsingError
from enterprise_rag.ingestion.chunk_strategies import build_default_strategy_registry
from enterprise_rag.ingestion.loaders.base import RawBlock
from enterprise_rag.ingestion.loaders.pdf_loader import PDFLoader
from enterprise_rag.ingestion.ocr import OCRResult
from enterprise_rag.ingestion.semantic_chunker import ChunkingContext
from enterprise_rag.ingestion.structure_parser import StructuredUnit, estimate_tokens


class _FakePDFPage:
    """中文：提供可控文本层的最小 PDF 页面测试替身。

    English: Provide a minimal PDF page test double with a controlled text layer.
    """

    def __init__(self, text: str) -> None:
        """中文：保存该物理页应返回的文本。

        English: Store the text returned for this physical page.
        """

        self._text = text

    def extract_text(self) -> str:
        """中文：返回预设的页面文本层。

        English: Return the predefined page text layer.
        """

        return self._text


class _FakePDFReader:
    """中文：构造一页原生文本与一页扫描内容组成的混合 PDF。

    English: Model a hybrid PDF containing one native-text page and one scanned page.
    """

    is_encrypted = False

    def __init__(self, _path: Path) -> None:
        """中文：忽略测试路径并创建固定页面序列。

        English: Ignore the test path and create the fixed page sequence.
        """

        self.pages = (_FakePDFPage("原生文本第一页内容"), _FakePDFPage(""))


class _FakeOCRProvider:
    """中文：仅为混合 PDF 的缺失第二页返回高置信度 OCR 结果。

    English: Return high-confidence OCR text only for the missing second hybrid-PDF page.
    """

    def extract_pdf(self, _path: Path) -> OCRResult:
        """中文：生成保留第二页物理页码的 OCR 结果。

        English: Produce OCR output preserving the physical page number two.
        """

        return OCRResult(
            blocks=(RawBlock("扫描第二页识别内容", "page", page_number=2),),
            mean_confidence=0.98,
            provider_version="fake-ocr-v1",
        )


def _unit(text: str, kind: str = "paragraph") -> StructuredUnit:
    """中文：构建具有稳定 Token 估算的紧凑测试结构单元。

    English: Build a compact test unit with a deterministic token estimate.
    """

    return StructuredUnit(
        text=text,
        kind=kind,
        heading_path=(),
        page_number=1,
        token_count=estimate_tokens(text),
    )


def _context() -> ChunkingContext:
    """中文：构建跨策略共享的固定 Chunk 身份上下文。

    English: Build a fixed chunk identity context shared across strategy tests.
    """

    return ChunkingContext("tenant-a", "source-a", "document-a", "version-a")


def test_manual_strategy_preserves_warning_and_step_roles() -> None:
    """中文：确认说明书策略识别标题、警告和步骤并写入 Chunk 元数据。

    English: Ensure the manual strategy records heading, warning, and step structural roles.
    """

    # 中文：变量 `strategy` 由资料源画像解析，而非根据文件扩展名猜测。
    # English: Strategy resolves from the source profile rather than the file extension.
    strategy = build_default_strategy_registry(5, 30, 80).resolve(ContentProfile.MANUAL)
    chunks = strategy.chunk(
        (
            _unit("第一章 安装准备"),
            _unit("警告：操作前必须断开设备电源。"),
            _unit("步骤1 检查电源指示灯。"),
            _unit("步骤2 连接接地线。"),
        ),
        _context(),
    )

    assert chunks
    assert all(chunk.metadata["content_profile"] == "manual" for chunk in chunks)
    assert any("warning" in chunk.metadata["unit_types"] for chunk in chunks)
    assert any("step" in chunk.metadata["unit_types"] for chunk in chunks)


def test_technical_strategy_identifies_api_and_configuration_units() -> None:
    """中文：确认技术文档策略识别 API 端点和配置项。

    English: Ensure the technical-document strategy identifies APIs and configuration entries.
    """

    strategy = build_default_strategy_registry(5, 30, 80).resolve(ContentProfile.TECHNICAL_DOC)
    chunks = strategy.chunk(
        (
            _unit("## Authentication"),
            _unit("POST /v1/token"),
            _unit("request_timeout: 30"),
        ),
        _context(),
    )

    unit_types = {unit_type for chunk in chunks for unit_type in chunk.metadata["unit_types"]}
    assert "api_section" in unit_types
    assert "config" in unit_types
    assert all(chunk.chunker_version == "technical-document-v4" for chunk in chunks)


def test_scanned_pdf_is_routed_to_needs_ocr(tmp_path: Path) -> None:
    """中文：确认没有文本层的 PDF 返回稳定 OCR 需求错误码。

    English: Ensure a PDF without a text layer returns the stable OCR-required error code.
    """

    # 中文：变量 `pdf_path` 是仅含空白图形页、没有文本层的最小扫描件替身。
    # English: PDF path is a minimal image-like blank page without an extractable text layer.
    pdf_path = tmp_path / "scanned.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    with pdf_path.open("wb") as target:
        writer.write(target)

    with pytest.raises(ParsingError) as captured:
        PDFLoader().load(pdf_path, pdf_path.name, "pdf")

    assert captured.value.detail.code == "PDF_OCR_REQUIRED"


def test_hybrid_pdf_uses_native_text_and_ocr_without_dropping_pages(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """中文：确认混合 PDF 保留原生页并用 OCR 补齐缺页，不会静默发布残缺索引。

    English: Ensure hybrid PDFs preserve native pages and OCR missing pages without silently
    publishing incomplete content.
    """

    # 中文：关键变量 `pdf_path` 只承担接口路径，不需要真实 PDF 字节。
    # English: Key variable `pdf_path` supplies the loader interface; fake parsing needs no bytes.
    pdf_path = tmp_path / "hybrid.pdf"
    monkeypatch.setattr(pdf_loader_module, "PdfReader", _FakePDFReader)

    loaded = PDFLoader(_FakeOCRProvider()).load(pdf_path, pdf_path.name, "pdf")

    assert tuple(block.page_number for block in loaded.blocks) == (1, 2)
    assert loaded.blocks[0].text == "原生文本第一页内容"
    assert loaded.blocks[1].text == "扫描第二页识别内容"
    assert loaded.metadata["ocr_applied"] is True
    assert loaded.metadata["ocr_page_numbers"] == [2]


def test_hybrid_pdf_without_ocr_is_rejected_as_a_whole(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """中文：确认没有 OCR 适配器时混合 PDF 整体拒绝，而不是只索引文本页。

    English: Ensure a hybrid PDF is rejected as a whole without OCR instead of indexing only
    its native-text pages.
    """

    pdf_path = tmp_path / "hybrid-without-ocr.pdf"
    monkeypatch.setattr(pdf_loader_module, "PdfReader", _FakePDFReader)

    with pytest.raises(ParsingError) as captured:
        PDFLoader().load(pdf_path, pdf_path.name, "pdf")

    assert captured.value.detail.code == "PDF_OCR_REQUIRED"
    assert captured.value.detail.context["missing_pages"] == "2"
