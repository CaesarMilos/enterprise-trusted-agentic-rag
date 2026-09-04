"""中文：验证统一规范文档对规则、技术手册和流程指南的通用适配。

English: Verify generic normalized-document adaptation for rules, manuals, and procedures.
"""

from __future__ import annotations

import pytest

from enterprise_rag.core.enums import CanonicalContentProfile, StructureType
from enterprise_rag.ingestion.cleaner import CleanedDocument, CleaningStats
from enterprise_rag.ingestion.loaders.base import RawBlock
from enterprise_rag.ingestion.normalization import NormalizedDocumentBuilder


def _cleaned(*texts: str, media_type: str = "txt") -> CleanedDocument:
    """中文：按输入文本创建最小规范化前文档。

    English: Create a minimal pre-normalization document from input passages.
    """

    blocks = tuple(
        RawBlock(text=text, page_number=index + 1, metadata={"block_id": f"b-{index}"})
        for index, text in enumerate(texts)
    )
    character_count = sum(len(text) for text in texts)
    return CleanedDocument(
        filename="reference.txt",
        media_type=media_type,
        blocks=blocks,
        metadata={},
        stats=CleaningStats(character_count, character_count, 0),
    )


@pytest.mark.parametrize(
    ("profile", "texts", "expected"),
    (
        (
            CanonicalContentProfile.NUMBERED_RULE_DOCUMENT,
            ("第一章 总则", "第八条 业务活动不得违反强制要求。"),
            (StructureType.HEADING, StructureType.NUMBERED_CLAUSE),
        ),
        (
            CanonicalContentProfile.SECTIONED_TECHNICAL_MANUAL,
            ("WARNING Disconnect power before service.", "参数 额定电压 220V"),
            (StructureType.WARNING, StructureType.PARAMETER_TABLE),
        ),
        (
            CanonicalContentProfile.PROCEDURE_GUIDE,
            ("前提 已完成身份校验", "步骤 1 打开控制面板"),
            (StructureType.PREREQUISITE, StructureType.PROCEDURE_STEP),
        ),
    ),
)
def test_generic_adapters_assign_reusable_structure_roles(
    profile: CanonicalContentProfile,
    texts: tuple[str, ...],
    expected: tuple[StructureType, ...],
) -> None:
    """中文：不同说明/指示文档复用同一规范模型，只替换 Profile 适配器。

    English: Different explanatory/instructional documents reuse one model and vary only adapter.
    """

    document = NormalizedDocumentBuilder().build(_cleaned(*texts), profile)

    assert tuple(block.structure_type for block in document.blocks) == expected
    assert all(
        document.text[block.locator.normalized.start : block.locator.normalized.end] == block.text
        for block in document.blocks
    )


def test_pdf_locator_is_explicitly_approximate_after_reflow() -> None:
    """中文：PDF 清洗后不得把页级映射伪装成精确原始字符坐标。

    English: PDF cleaning must not misrepresent page-level mapping as exact original characters.
    """

    document = NormalizedDocumentBuilder().build(
        _cleaned("2.1 安装要求", media_type="pdf"),
        CanonicalContentProfile.SECTIONED_TECHNICAL_MANUAL,
    )

    assert document.blocks[0].locator.mapping_quality.value == "approximate"
    assert document.blocks[0].locator.original.page_start == 1
