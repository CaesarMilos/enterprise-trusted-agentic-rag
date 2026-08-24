"""中文：在 OCR 系统依赖可用时验证真实 PyMuPDF/Tesseract PDF 链路。

English: Verify the real PyMuPDF/Tesseract PDF path when optional OCR system dependencies exist.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from enterprise_rag.infrastructure.ocr.tesseract_provider import TesseractOCRProvider


def _english_test_font() -> Path | None:
    """中文：返回容器或常见 Linux 开发机上可用的真实字体。

    English: Return a real font available in the container or a common Linux workstation.
    """

    candidates = (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    )
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def test_real_tesseract_extracts_a_scanned_pdf_page(tmp_path: Path) -> None:
    """中文：用真实图像 PDF 确认渲染、Tesseract 和页码定位端到端可用。

    English: Use a real image PDF to verify rendering, Tesseract, and page locations end to end.
    """

    if shutil.which("tesseract") is None:
        pytest.skip("system Tesseract is not installed")
    pytest.importorskip("fitz")
    pytest.importorskip("pytesseract")
    image_module = pytest.importorskip("PIL.Image")
    image_draw_module = pytest.importorskip("PIL.ImageDraw")
    image_font_module = pytest.importorskip("PIL.ImageFont")
    font_path = _english_test_font()
    if font_path is None:
        pytest.skip("a readable test font is not installed")

    # 中文：关键变量 `image` 制造没有文本层的真实扫描页。
    # English: Key variable `image` creates a real scanned page with no PDF text layer.
    image = image_module.new("RGB", (1400, 420), "white")
    drawing = image_draw_module.Draw(image)
    font = image_font_module.truetype(str(font_path), 64)
    drawing.text((70, 150), "EQUIPMENT MANUAL 12345", fill="black", font=font)
    pdf_path = tmp_path / "scanned-manual.pdf"
    image.save(pdf_path, "PDF", resolution=180.0)

    result = TesseractOCRProvider(language="eng", dpi=220).extract_pdf(pdf_path)

    assert len(result.blocks) == 1
    assert result.blocks[0].page_number == 1
    assert len(result.blocks[0].text.strip()) >= 10
    assert result.mean_confidence > 0.0
