"""中文：把不同文件格式统一为可定位、可适配且与具体文档无关的规范结构。

English: Normalize file formats into locatable, adaptable structures independent of any one
document.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Protocol, cast

from enterprise_rag.core.enums import CanonicalContentProfile, StructureType
from enterprise_rag.core.ids import content_sha256
from enterprise_rag.domain.locators import (
    DisplayLocator,
    LocatorBundle,
    LocatorMappingQuality,
    NormalizedRange,
    OriginalLocator,
)
from enterprise_rag.ingestion.cleaner import CleanedDocument
from enterprise_rag.ingestion.loaders.base import RawBlock

# 中文：通用编号锚点覆盖法规条款、手册章节和流程步骤，不包含具体法典名称。
# English: Generic numbered anchors cover clauses, manual sections, and procedure steps without
# naming any specific corpus.
_NUMBERED_RULE = re.compile(
    r"^(第\s*[零〇一二两三四五六七八九十百千万亿0-9]+\s*[条款]|"
    r"(?:Article|Section|Clause)\s+[A-Za-z0-9_.-]+|\d+(?:\.\d+)+)",
    re.I,
)
_HEADING = re.compile(
    r"^(?:第\s*[零〇一二两三四五六七八九十百千万亿0-9]+\s*[编章节]|"
    r"#{1,6}\s*|\d+(?:\.\d+)*\s+[A-Za-z\u3400-\u9fff])",
    re.I,
)
_STEP = re.compile(
    r"^(?:步骤\s*[零〇一二三四五六七八九十0-9]+|"
    r"第\s*[零〇一二三四五六七八九十0-9]+\s*步|Step\s+\d+|\d+[.)、])",
    re.I,
)
_WARNING = re.compile(r"^(?:危险|警告|注意|重要|DANGER|WARNING|CAUTION|NOTICE)", re.I)
_PREREQUISITE = re.compile(r"^(?:前提|准备|先决条件|Prerequisite|Before you begin)", re.I)
_TROUBLESHOOTING = re.compile(r"^(?:故障|问题|症状|原因|解决方案|Troubleshoot|Symptom)", re.I)
_PARAMETER = re.compile(r"^(?:参数|规格|型号|额定|默认值|取值范围|Parameter|Specification)", re.I)
_EXCEPTION = re.compile(r"^(?:但是|但书|除非|例外|Except|Unless)", re.I)


@dataclass(frozen=True, slots=True)
class NormalizedBlock:
    """中文：表示带三层坐标和通用结构角色的规范文本块。

    English: Represent a normalized text block with three-layer location and generic structure.
    """

    # 中文：`id` 由规范文本、序号和定位信息确定，重处理相同输入保持稳定。
    # English: `id` derives from normalized text, ordinal, and locator for stable reprocessing.
    id: str
    # 中文：`ordinal` 是文档内零基有序位置。
    # English: `ordinal` is the zero-based document order.
    ordinal: int
    # 中文：`text` 是清洗后的可引用正文。
    # English: `text` is cleaned citable body content.
    text: str
    # 中文：`structure_type` 使用跨法规、手册和 SOP 的通用语义角色。
    # English: `structure_type` uses a generic semantic role across rules, manuals, and SOPs.
    structure_type: StructureType
    # 中文：`locator` 同时保留原文件、规范文本和展示位置。
    # English: `locator` preserves original, normalized, and display positions together.
    locator: LocatorBundle
    # 中文：`hard_boundary_key` 限制 Parent/局部窗口不得跨越独立结构单元。
    # English: `hard_boundary_key` prevents parent/local windows crossing independent structures.
    hard_boundary_key: str | None = None
    # 中文：`metadata` 仅保存安全、格式中立的补充值。
    # English: `metadata` contains only safe format-neutral supplementary values.
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """中文：校验序号、正文和规范坐标的一致性。

        English: Validate ordinal, body text, and normalized-coordinate consistency.
        """

        if self.ordinal < 0 or not self.text:
            raise ValueError("normalized block requires a nonnegative ordinal and nonempty text")
        if self.locator.normalized.end - self.locator.normalized.start != len(self.text):
            raise ValueError("normalized block range length must equal text length")


@dataclass(frozen=True, slots=True)
class NormalizedDocument:
    """中文：冻结接入后供结构适配、切块、引用和审计共享的文档表示。

    English: Freeze the shared representation used by adaptation, chunking, citation, and audit.
    """

    filename: str
    media_type: str
    text: str
    blocks: tuple[NormalizedBlock, ...]
    profile: CanonicalContentProfile
    normalizer_version: str = "normalized-document-v1"
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """中文：确保块顺序、范围和全文切片完全一致。

        English: Ensure block order, ranges, and full-text slices are exactly consistent.
        """

        if tuple(block.ordinal for block in self.blocks) != tuple(range(len(self.blocks))):
            raise ValueError("normalized block ordinals must be contiguous")
        for block in self.blocks:
            span = block.locator.normalized
            if span.end > len(self.text) or self.text[span.start : span.end] != block.text:
                raise ValueError("normalized locator does not resolve to block text")

    def as_cleaned_blocks(self) -> tuple[RawBlock, ...]:
        """中文：为 V4 结构解析器生成兼容块，同时保留 V5 Locator 元数据。

        English: Produce V4-compatible parser blocks while retaining V5 locator metadata.
        """

        kind_map = {
            StructureType.GENERAL_PARAGRAPH: "paragraph",
            StructureType.PROCEDURE_STEP: "step",
            StructureType.PARAMETER_TABLE: "parameter",
            StructureType.TROUBLESHOOTING_ENTRY: "troubleshooting",
        }
        return tuple(
            RawBlock(
                text=block.text,
                kind=kind_map.get(block.structure_type, block.structure_type.value),
                page_number=block.locator.display.page_start,
                heading_level=(
                    len(block.locator.display.heading_path)
                    if block.structure_type is StructureType.HEADING
                    else None
                ),
                metadata={
                    **block.metadata,
                    "normalized_block_id": block.id,
                    "hard_boundary_key": block.hard_boundary_key,
                    "locator_mapping_quality": block.locator.mapping_quality.value,
                },
            )
            for block in self.blocks
        )


class StructureAdapter(Protocol):
    """中文：定义按通用 Profile 标注结构角色的适配器接口。

    English: Define the adapter interface assigning structural roles by generic profile.
    """

    profile: CanonicalContentProfile

    def adapt(self, document: NormalizedDocument) -> NormalizedDocument:
        """中文：返回只改变结构标注、不改变正文坐标的文档。

        English: Return a document changing structural labels without altering text coordinates.
        """


@dataclass(frozen=True, slots=True)
class RuleBasedStructureAdapter:
    """中文：用确定性通用规则标注结构，避免为某份展示文档硬编码。

    English: Apply deterministic generic rules without hard-coding a showcase document.
    """

    profile: CanonicalContentProfile
    rules: tuple[tuple[StructureType, re.Pattern[str]], ...]
    hard_types: frozenset[StructureType]

    def adapt(self, document: NormalizedDocument) -> NormalizedDocument:
        """中文：顺序匹配首条规则，并构造稳定硬边界键和展示锚点。

        English: Apply the first matching rule and create stable hard-boundary/display anchors.
        """

        active_heading: tuple[str, ...] = ()
        active_boundary: str | None = None
        adapted: list[NormalizedBlock] = []
        for block in document.blocks:
            matched_type = next(
                (structure for structure, pattern in self.rules if pattern.search(block.text)),
                block.structure_type,
            )
            anchor_match = _NUMBERED_RULE.search(block.text)
            anchor = anchor_match.group(0).replace(" ", "") if anchor_match else None
            if matched_type is StructureType.HEADING:
                active_heading = (block.text.replace("\n", " ")[:256],)
                active_boundary = block.id
            elif matched_type in {
                StructureType.NUMBERED_CLAUSE,
                StructureType.PROCEDURE_STEP,
                StructureType.TROUBLESHOOTING_ENTRY,
            }:
                active_boundary = anchor or block.id
            display = replace(
                block.locator.display,
                heading_path=active_heading or block.locator.display.heading_path,
                structural_anchor=anchor or block.locator.display.structural_anchor,
            )
            adapted.append(
                replace(
                    block,
                    structure_type=matched_type,
                    locator=replace(block.locator, display=display),
                    # 中文：后续子块继承最近的硬边界，直到新边界覆盖它。
                    # English: Descendants inherit the nearest hard boundary until replaced.
                    hard_boundary_key=active_boundary,
                )
            )
        return replace(document, blocks=tuple(adapted), profile=self.profile)


class StructureAdapterRegistry:
    """中文：按四种通用 Profile 解析唯一结构适配器。

    English: Resolve one structure adapter for each of the four generic profiles.
    """

    def __init__(self, adapters: tuple[StructureAdapter, ...]) -> None:
        """中文：拒绝 Profile 重复或缺失的适配器集合。

        English: Reject adapter sets with duplicate or missing profiles.
        """

        self._adapters = {adapter.profile: adapter for adapter in adapters}
        if set(self._adapters) != set(CanonicalContentProfile):
            raise ValueError("structure adapters must cover every canonical profile exactly once")

    def resolve(self, profile: CanonicalContentProfile) -> StructureAdapter:
        """中文：返回指定通用 Profile 的确定性适配器。

        English: Return the deterministic adapter for a canonical profile.
        """

        return self._adapters[profile]


class NormalizedDocumentBuilder:
    """中文：构建三层坐标并委托 Profile 适配器标注结构。

    English: Build three-layer locators and delegate structural labeling to a profile adapter.
    """

    def __init__(self, adapters: StructureAdapterRegistry | None = None) -> None:
        """中文：保存适配器注册表；默认覆盖规则、技术、流程和通用说明文档。

        English: Store an adapter registry covering rules, technical, procedure, and expository
        documents by default.
        """

        self._adapters = adapters or build_default_structure_adapters()

    def build(
        self,
        cleaned: CleanedDocument,
        profile: CanonicalContentProfile,
    ) -> NormalizedDocument:
        """中文：按块构造规范全文、稳定范围、原始定位和展示定位。

        English: Build normalized text, stable ranges, original locators, and display locators.
        """

        text = "\n".join(block.text for block in cleaned.blocks)
        offset = 0
        heading_path: tuple[str, ...] = ()
        blocks: list[NormalizedBlock] = []
        for ordinal, raw in enumerate(cleaned.blocks):
            if raw.kind == "heading":
                heading_path = (raw.text.replace("\n", " ")[:256],)
            start = offset
            end = start + len(raw.text)
            block_id = f"nblk-{content_sha256(f'{ordinal}:{start}:{raw.text}')[:24]}"
            # 中文：只有未删块且字符数未变的非 PDF 文本才能声称精确映射；
            # NFKC、空白清理、OCR 或 PDF 重排都会使原始坐标变为近似。
            # English: Exact mapping is claimed only for non-PDF text whose block and
            # character counts survived cleaning; NFKC, removal, OCR, or reflow is approximate.
            unchanged_plain_text = (
                cleaned.media_type != "pdf"
                and cleaned.stats.removed_blocks == 0
                and cleaned.stats.original_characters == cleaned.stats.cleaned_characters
            )
            mapping_quality = (
                LocatorMappingQuality.EXACT
                if unchanged_plain_text
                else LocatorMappingQuality.APPROXIMATE
            )
            blocks.append(
                NormalizedBlock(
                    id=block_id,
                    ordinal=ordinal,
                    text=raw.text,
                    structure_type=(
                        StructureType.HEADING
                        if raw.kind == "heading"
                        else StructureType.GENERAL_PARAGRAPH
                    ),
                    locator=LocatorBundle(
                        original=OriginalLocator(
                            page_start=raw.page_number,
                            page_end=raw.page_number,
                            block_ids=(str(raw.metadata.get("block_id", f"block-{ordinal}")),),
                        ),
                        normalized=NormalizedRange(
                            start,
                            end,
                            text_hash=content_sha256(raw.text),
                        ),
                        display=DisplayLocator(
                            title=cleaned.filename,
                            heading_path=heading_path,
                            page_start=raw.page_number,
                            page_end=raw.page_number,
                        ),
                        mapping_quality=mapping_quality,
                    ),
                    metadata={"loader_kind": raw.kind},
                )
            )
            offset = end + 1
        base = NormalizedDocument(
            filename=cleaned.filename,
            media_type=cleaned.media_type,
            text=text,
            blocks=tuple(blocks),
            profile=profile,
            metadata=dict(cleaned.metadata),
        )
        return self._adapters.resolve(profile).adapt(base)


def build_default_structure_adapters() -> StructureAdapterRegistry:
    """中文：构建不依赖具体法典、厂商或设备型号的四类适配器。

    English: Build four adapters independent of any specific code, vendor, or device model.
    """

    adapters = (
        cast(
            StructureAdapter,
            RuleBasedStructureAdapter(
                CanonicalContentProfile.NUMBERED_RULE_DOCUMENT,
                (
                    (StructureType.HEADING, _HEADING),
                    (StructureType.NUMBERED_CLAUSE, _NUMBERED_RULE),
                    (StructureType.EXCEPTION, _EXCEPTION),
                ),
                frozenset({StructureType.HEADING, StructureType.NUMBERED_CLAUSE}),
            ),
        ),
        cast(
            StructureAdapter,
            RuleBasedStructureAdapter(
                CanonicalContentProfile.SECTIONED_TECHNICAL_MANUAL,
                (
                    (StructureType.WARNING, _WARNING),
                    (StructureType.TROUBLESHOOTING_ENTRY, _TROUBLESHOOTING),
                    (StructureType.PARAMETER_TABLE, _PARAMETER),
                    (StructureType.HEADING, _HEADING),
                    (StructureType.PROCEDURE_STEP, _STEP),
                ),
                frozenset(
                    {
                        StructureType.HEADING,
                        StructureType.WARNING,
                        StructureType.TROUBLESHOOTING_ENTRY,
                    }
                ),
            ),
        ),
        cast(
            StructureAdapter,
            RuleBasedStructureAdapter(
                CanonicalContentProfile.PROCEDURE_GUIDE,
                (
                    (StructureType.WARNING, _WARNING),
                    (StructureType.PREREQUISITE, _PREREQUISITE),
                    (StructureType.PROCEDURE_STEP, _STEP),
                    (StructureType.TROUBLESHOOTING_ENTRY, _TROUBLESHOOTING),
                    (StructureType.HEADING, _HEADING),
                ),
                frozenset(
                    {
                        StructureType.HEADING,
                        StructureType.PROCEDURE_STEP,
                        StructureType.WARNING,
                    }
                ),
            ),
        ),
        cast(
            StructureAdapter,
            RuleBasedStructureAdapter(
                CanonicalContentProfile.GENERAL_EXPOSITORY,
                ((StructureType.HEADING, _HEADING),),
                frozenset({StructureType.HEADING}),
            ),
        ),
    )
    return StructureAdapterRegistry(adapters)
