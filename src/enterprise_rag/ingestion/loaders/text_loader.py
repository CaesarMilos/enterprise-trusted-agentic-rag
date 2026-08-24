"""中文：本模块负责实现“文本加载器”相关功能。

English: Load plain-text documents with deterministic encoding fallback.
"""

from __future__ import annotations

from pathlib import Path

from enterprise_rag.core.enums import ErrorCategory
from enterprise_rag.core.exceptions import ParsingError, error_detail
from enterprise_rag.ingestion.loaders.base import LoadedDocument, RawBlock


class TextLoader:
    """中文：该类用于表示或实现“文本加载器（TextLoader）”的职责。

    English: Decode a text file and preserve paragraph order.
    """

    @property
    def media_types(self) -> frozenset[str]:
        """中文：该函数或方法负责“媒体类型”相关处理。

        English: Return the plain-text type supported by this loader.
        """

        return frozenset({"txt"})

    def load(self, path: Path, filename: str, media_type: str) -> LoadedDocument:
        """中文：该函数或方法负责“加载并解析目标数据”相关处理。

        English: Decode UTF-family text and emit non-empty paragraph blocks.
        """

        # 中文：变量 `payload` 用于保存“载荷”相关数据；其精确定义与约束见下方英文说明。
        # English: Raw bytes allow deterministic encoding attempts without platform
        #   defaults.
        payload = path.read_bytes()
        # 中文：变量 `decoded_text` 用于保存“`decoded`文本”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Common encodings are attempted in a stable order.
        decoded_text: str | None = None
        # 中文：变量 `selected_encoding` 用于保存“选中的`encoding`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Encoding label is retained for safe ingestion metadata.
        selected_encoding: str | None = None
        for encoding in ("utf-8-sig", "utf-16", "gb18030"):
            try:
                decoded_text = payload.decode(encoding)
                selected_encoding = encoding
                break
            except UnicodeDecodeError:
                continue
        if decoded_text is None or selected_encoding is None:
            raise ParsingError(
                error_detail(
                    "TEXT_DECODING_FAILED",
                    ErrorCategory.PARSING,
                    "The text document encoding could not be determined.",
                )
            )
        # 中文：变量 `paragraphs` 用于保存“`paragraphs`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Blank-line separation retains paragraph units for structure-aware
        #   chunking.
        paragraphs = tuple(
            RawBlock(text=paragraph.strip(), kind="paragraph")
            for paragraph in decoded_text.replace("\r\n", "\n").split("\n\n")
            if paragraph.strip()
        )
        return LoadedDocument(
            filename=filename,
            media_type=media_type,
            blocks=paragraphs,
            metadata={"encoding": selected_encoding, "block_count": len(paragraphs)},
        )
