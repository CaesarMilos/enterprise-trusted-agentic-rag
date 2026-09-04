"""中文：本模块用 PyMuPDF 渲染 PDF，并通过本地 Tesseract 完成逐页 OCR。

English: Render PDF pages with PyMuPDF and perform page-level OCR with local Tesseract.
"""

from __future__ import annotations

from collections import defaultdict
from io import BytesIO
from pathlib import Path

from enterprise_rag.ingestion.loaders.base import RawBlock
from enterprise_rag.ingestion.ocr import OCRResult


class TesseractOCRProvider:
    """中文：实现完全本地、按页保留定位和置信度的 PDF OCR 适配器。

    English: Implement fully local PDF OCR with page locations and confidence measurements.
    """

    def __init__(self, language: str = "chi_sim+eng", dpi: int = 250) -> None:
        """中文：保存 Tesseract 语言包与 PDF 渲染分辨率。

        English: Store the Tesseract language packs and PDF rendering resolution.
        """

        if dpi < 120 or dpi > 600:
            raise ValueError("OCR dpi must be between 120 and 600")
        self._language = language
        self._dpi = dpi

    def extract_pdf(self, path: Path) -> OCRResult:
        """中文：渲染并识别每一物理页，返回有序文本块和平均有效置信度。

        English: Render and recognize each physical page, returning ordered text and mean valid
        confidence.
        """

        try:
            import fitz
            import pytesseract
            from PIL import Image
            from pytesseract import Output
        except ImportError as exc:
            raise RuntimeError(
                "OCR extras are required: install the project with the 'ocr' extra"
            ) from exc

        blocks: list[RawBlock] = []
        confidences: list[float] = []
        document = fitz.open(path)
        try:
            for page_number, page in enumerate(document, start=1):
                scale = self._dpi / 72.0
                pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                image = Image.open(BytesIO(pixmap.tobytes("png")))
                data = pytesseract.image_to_data(
                    image,
                    lang=self._language,
                    output_type=Output.DICT,
                )
                text = self._data_to_text(data)
                page_confidences = self._valid_confidences(data)
                confidences.extend(page_confidences)
                blocks.append(
                    RawBlock(
                        text=text,
                        kind="page",
                        page_number=page_number,
                        metadata={
                            "ocr_applied": True,
                            "ocr_dpi": self._dpi,
                            "ocr_language": self._language,
                        },
                    )
                )
        finally:
            document.close()
        mean_confidence = sum(confidences) / len(confidences) / 100.0 if confidences else 0.0
        version = f"tesseract-{pytesseract.get_tesseract_version()}:{self._language}:dpi{self._dpi}"
        return OCRResult(tuple(blocks), mean_confidence, version)

    @staticmethod
    def _data_to_text(data: dict[str, list[object]]) -> str:
        """中文：按 Tesseract 页块、段落和行号重建稳定阅读顺序文本。

        English: Reconstruct stable reading-order text from Tesseract block, paragraph, and line
        identifiers.
        """

        lines: dict[tuple[int, int, int], list[str]] = defaultdict(list)
        texts = data.get("text", [])
        block_numbers = data.get("block_num", [])
        paragraph_numbers = data.get("par_num", [])
        line_numbers = data.get("line_num", [])
        for index, raw_text in enumerate(texts):
            word = str(raw_text).strip()
            if not word:
                continue
            if index >= min(
                len(block_numbers),
                len(paragraph_numbers),
                len(line_numbers),
            ):
                continue
            # 中文：关键变量 `key` 通过字符串中间层安全收窄 OCR 的 object 值。
            # English: Key variable `key` safely narrows OCR object values through strings.
            try:
                key = (
                    int(str(block_numbers[index])),
                    int(str(paragraph_numbers[index])),
                    int(str(line_numbers[index])),
                )
            except ValueError:
                continue
            lines[key].append(word)
        return "\n".join(_join_ocr_words(words) for _key, words in sorted(lines.items()))

    @staticmethod
    def _valid_confidences(data: dict[str, list[object]]) -> tuple[float, ...]:
        """中文：过滤无效占位值并返回零到一百之间的 OCR 词置信度。

        English: Filter invalid placeholders and return OCR word confidences from zero to one
        hundred.
        """

        values: list[float] = []
        for raw_value in data.get("conf", []):
            try:
                value = float(str(raw_value))
            except (TypeError, ValueError):
                continue
            if 0.0 <= value <= 100.0:
                values.append(value)
        return tuple(values)


def _join_ocr_words(words: list[str]) -> str:
    """中文：中文相邻词不插入空格，拉丁词之间保留一个空格。

    English: Join adjacent CJK tokens without spaces and preserve one space between Latin words.
    """

    output = ""
    for word in words:
        separator = " " if output and output[-1:].isascii() and word[:1].isascii() else ""
        output = f"{output}{separator}{word}"
    return output
