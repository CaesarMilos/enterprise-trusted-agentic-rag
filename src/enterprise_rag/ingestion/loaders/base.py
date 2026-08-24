"""中文：本模块负责实现“基础”相关功能。

English: Define normalized loader output and the common document-loader protocol.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class RawBlock:
    """中文：该类用于表示或实现“原始内容块（RawBlock）”的职责。

    English: Represent one ordered block extracted from an original document.
    """

    # 中文：变量 `text` 用于保存“文本”相关数据；其精确定义与约束见下方英文说明。
    # English: Block text in original reading order.
    text: str
    # 中文：变量 `kind` 用于保存“`kind`”相关数据；其精确定义与约束见下方英文说明。
    # English: Semantic block kind such as heading, paragraph, table, list, or code.
    kind: str = "paragraph"
    # 中文：变量 `page_number` 用于保存“`page``number`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: One-based page number when the source format supplies pages.
    page_number: int | None = None
    # 中文：变量 `heading_level` 用于保存“`heading``level`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Heading depth for heading blocks.
    heading_level: int | None = None
    # 中文：变量 `metadata` 用于保存“元数据”相关数据；其精确定义与约束见下方英文说明。
    # English: Format-specific values safe for downstream metadata.
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LoadedDocument:
    """中文：该类用于表示或实现“已加载的文档（LoadedDocument）”的职责。

    English: Represent deterministic ordered content returned by a format loader.
    """

    # 中文：变量 `filename` 用于保存“`filename`”相关数据；其精确定义与约束见下方英文说明。
    # English: Safe original display filename.
    filename: str
    # 中文：变量 `media_type` 用于保存“`media``type`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Verified lowercase document type.
    media_type: str
    # 中文：变量 `blocks` 用于保存“`blocks`”相关数据；其精确定义与约束见下方英文说明。
    # English: Ordered extracted content blocks.
    blocks: tuple[RawBlock, ...]
    # 中文：变量 `metadata` 用于保存“元数据”相关数据；其精确定义与约束见下方英文说明。
    # English: Loader-level metadata such as page or paragraph count.
    metadata: dict[str, Any] = field(default_factory=dict)


class DocumentLoader(Protocol):
    """中文：该类用于表示或实现“文档加载器（DocumentLoader）”的职责。

    English: Load one validated local document into ordered format-neutral blocks.
    """

    @property
    def media_types(self) -> frozenset[str]:
        """中文：该函数或方法负责“媒体类型”相关处理。

        English: Return the lowercase document types supported by this loader.
        """

    def load(self, path: Path, filename: str, media_type: str) -> LoadedDocument:
        """中文：该函数或方法负责“加载并解析目标数据”相关处理。

        English: Extract deterministic blocks while preserving available source positions.
        """
