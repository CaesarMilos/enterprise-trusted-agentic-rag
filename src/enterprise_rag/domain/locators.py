"""中文：定义可追溯到原文件、规范化文本和用户展示位置的三层坐标。

English: Define three-layer locators for original files, normalized text, and display positions.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum


class LocatorMappingQuality(StrEnum):
    """中文：说明规范化文本到原始文件坐标的映射精度。

    English: Describe mapping precision from normalized text back to the original file.
    """

    EXACT = "exact"
    APPROXIMATE = "approximate"
    PAGE_ONLY = "page_only"


@dataclass(frozen=True, slots=True)
class OCRBox:
    """中文：保存 OCR 文本在页面上的归一化边界框。

    English: Store a normalized page bounding box for OCR-derived text.
    """

    page: int
    left: float
    top: float
    right: float
    bottom: float

    def __post_init__(self) -> None:
        """中文：校验页码和零到一范围内的矩形坐标。

        English: Validate page number and rectangular coordinates within the unit interval.
        """

        if self.page < 1:
            raise ValueError("OCR box page must start at one")
        coordinates = (self.left, self.top, self.right, self.bottom)
        if not all(0.0 <= coordinate <= 1.0 for coordinate in coordinates):
            raise ValueError("OCR box coordinates must be within [0, 1]")
        if self.right <= self.left or self.bottom <= self.top:
            raise ValueError("OCR box must have positive width and height")


@dataclass(frozen=True, slots=True)
class OriginalLocator:
    """中文：描述原文件中的页、块、行或 OCR 框位置。

    English: Describe page, block, line, or OCR-box positions in the original file.
    """

    page_start: int | None = None
    page_end: int | None = None
    block_ids: tuple[str, ...] = ()
    line_start: int | None = None
    line_end: int | None = None
    ocr_boxes: tuple[OCRBox, ...] = ()

    def __post_init__(self) -> None:
        """中文：拒绝空坐标和反向页码或行号范围。

        English: Reject empty locators and reversed page or line ranges.
        """

        if self.page_start is not None and self.page_start < 1:
            raise ValueError("original page_start must be at least one")
        if self.page_end is not None and self.page_end < 1:
            raise ValueError("original page_end must be at least one")
        if self.page_start is not None and self.page_end is not None:
            if self.page_end < self.page_start:
                raise ValueError("original page range cannot be reversed")
        if self.line_start is not None and self.line_start < 0:
            raise ValueError("original line_start cannot be negative")
        if self.line_end is not None and self.line_end < 0:
            raise ValueError("original line_end cannot be negative")
        if self.line_start is not None and self.line_end is not None:
            if self.line_end < self.line_start:
                raise ValueError("original line range cannot be reversed")
        if not any(
            (
                self.page_start is not None,
                self.block_ids,
                self.line_start is not None,
                self.ocr_boxes,
            )
        ):
            raise ValueError("original locator requires a page, block, line, or OCR box")


@dataclass(frozen=True, slots=True)
class NormalizedRange:
    """中文：保存规范化全文中左闭右开的字符区间。

    English: Store a half-open character interval in the normalized document text.
    """

    start: int
    end: int
    text_hash: str | None = None

    def __post_init__(self) -> None:
        """中文：确保规范化字符范围非空且方向正确。

        English: Ensure the normalized character range is non-empty and ordered.
        """

        if self.start < 0 or self.end <= self.start:
            raise ValueError("normalized range must satisfy 0 <= start < end")


@dataclass(frozen=True, slots=True)
class DisplayLocator:
    """中文：保存面向用户的标题、结构锚点和页码标签。

    English: Store user-facing title, structure anchor, and page labels.
    """

    title: str | None = None
    heading_path: tuple[str, ...] = ()
    structural_anchor: str | None = None
    page_start: int | None = None
    page_end: int | None = None

    def __post_init__(self) -> None:
        """中文：校验展示页码并限制异常长标题元数据。

        English: Validate display pages and bound unexpectedly long title metadata.
        """

        if self.title is not None and len(self.title) > 512:
            raise ValueError("display title cannot exceed 512 characters")
        if any(len(heading) > 256 for heading in self.heading_path):
            raise ValueError("display heading cannot exceed 256 characters")
        if self.page_start is not None and self.page_start < 1:
            raise ValueError("display page_start must be at least one")
        if self.page_end is not None and self.page_end < 1:
            raise ValueError("display page_end must be at least one")
        if self.page_start is not None and self.page_end is not None:
            if self.page_end < self.page_start:
                raise ValueError("display page range cannot be reversed")


@dataclass(frozen=True, slots=True)
class LocatorBundle:
    """中文：绑定同一证据的原始、规范化和展示坐标。

    English: Bind original, normalized, and display coordinates for the same evidence.
    """

    original: OriginalLocator
    normalized: NormalizedRange
    display: DisplayLocator
    mapping_quality: LocatorMappingQuality


def merge_locator_bundles(locators: Sequence[LocatorBundle]) -> LocatorBundle:
    """中文：合并相邻结构坐标并采用其中最弱的映射质量。

    English: Merge adjacent structural locators and preserve their weakest mapping quality.
    """

    if not locators:
        raise ValueError("at least one locator is required for merging")
    # 中文：质量等级从弱到强排序，合并结果必须采用最保守等级。
    # English: Quality ranks from weakest to strongest; merging keeps the conservative level.
    quality_rank = {
        LocatorMappingQuality.PAGE_ONLY: 0,
        LocatorMappingQuality.APPROXIMATE: 1,
        LocatorMappingQuality.EXACT: 2,
    }
    weakest_quality = min(locators, key=lambda item: quality_rank[item.mapping_quality])
    page_starts = [item.original.page_start for item in locators if item.original.page_start]
    page_ends = [item.original.page_end for item in locators if item.original.page_end]
    block_ids = tuple(
        dict.fromkeys(block_id for item in locators for block_id in item.original.block_ids)
    )
    # 中文：标题路径取最长公共前缀，避免把不同章节伪装成同一锚点。
    # English: Heading path uses the longest common prefix to avoid false shared anchors.
    common_headings = list(locators[0].display.heading_path)
    for item in locators[1:]:
        common_length = 0
        for left, right in zip(common_headings, item.display.heading_path, strict=False):
            if left != right:
                break
            common_length += 1
        common_headings = common_headings[:common_length]
    anchors = {item.display.structural_anchor for item in locators}
    shared_anchor = anchors.pop() if len(anchors) == 1 else None
    normalized_start = min(item.normalized.start for item in locators)
    normalized_end = max(item.normalized.end for item in locators)
    return LocatorBundle(
        original=OriginalLocator(
            page_start=min(page_starts) if page_starts else None,
            page_end=max(page_ends) if page_ends else None,
            block_ids=block_ids,
            ocr_boxes=tuple(box for item in locators for box in item.original.ocr_boxes),
        ),
        normalized=NormalizedRange(normalized_start, normalized_end),
        display=DisplayLocator(
            title=locators[0].display.title,
            heading_path=tuple(common_headings),
            structural_anchor=shared_anchor,
            page_start=min(page_starts) if page_starts else None,
            page_end=max(page_ends) if page_ends else None,
        ),
        mapping_quality=weakest_quality.mapping_quality,
    )
