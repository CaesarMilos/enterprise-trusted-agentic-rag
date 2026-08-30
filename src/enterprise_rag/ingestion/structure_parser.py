"""中文：本模块负责实现“结构解析器”相关功能。

English: Convert cleaned format blocks into sentence-aware units with heading paths and pages.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from enterprise_rag.ingestion.chunking.chinese_sentence_splitter import ChineseSentenceSplitter
from enterprise_rag.ingestion.cleaner import CleanedDocument

# 中文：无状态切句器在所有格式解析器间复用，确保相同文本得到相同句界。
# English: One stateless splitter keeps sentence boundaries identical across file formats.
_SENTENCE_SPLITTER = ChineseSentenceSplitter()
# 中文：变量 `_TOKEN_PATTERN` 用于保存“词元`pattern`”相关数据；
# 其精确定义与约束见下方英文说明。
# English: Token estimate counts CJK characters, Latin words, and standalone punctuation.
_TOKEN_PATTERN = re.compile(r"[\u3400-\u9fff]|[A-Za-z0-9_]+|[^\s]")
# 中文：编号结构是说明书、规范和法典共享的强定位信号。
# English: Numbered structures are strong shared anchors across manuals and references.
_NUMBERED_STRUCTURE = re.compile(
    r"^(第\s*[零〇一二两三四五六七八九十百千万亿0-9]+\s*[章节条款步]|"
    r"(?:步骤|第)\s*[零〇一二两三四五六七八九十百千万亿0-9]+\s*(?:步)?|"
    r"[（(][一二三四五六七八九十0-9]+[）)]|\d+(?:\.\d+)*[.)、])"
)


def _split_prose(text: str) -> tuple[str, ...]:
    """中文：先保留 PDF/TXT 行级结构，再按中英文句末标点生成候选单元。

    English: Preserve PDF/TXT line structure before splitting candidate sentence units.
    """

    # 中文：变量 `lines` 让条目编号、警告和配置行能够被专用策略单独识别。
    # English: Lines expose numbered steps, warnings, and configuration entries to strategies.
    lines = tuple(line.strip() for line in text.splitlines() if line.strip()) or (text.strip(),)
    return tuple(part for line in lines for part in _SENTENCE_SPLITTER.split(line))


def estimate_tokens(text: str) -> int:
    """中文：该函数或方法负责“`estimate`词元”相关处理。

    English: Return a deterministic provider-independent token-count estimate.
    """

    return len(_TOKEN_PATTERN.findall(text))


@dataclass(frozen=True, slots=True)
class StructuredUnit:
    """中文：该类用于表示或实现“结构化单元（StructuredUnit）”的职责。

    English: Represent one chunkable text unit with restored source structure.
    """

    # 中文：变量 `text` 用于保存“文本”相关数据；其精确定义与约束见下方英文说明。
    # English: Normalized unit text.
    text: str
    # 中文：变量 `kind` 用于保存“`kind`”相关数据；其精确定义与约束见下方英文说明。
    # English: Semantic unit kind inherited from the loader.
    kind: str
    # 中文：变量 `heading_path` 用于保存“`heading``path`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Hierarchical heading path active at this unit.
    heading_path: tuple[str, ...]
    # 中文：变量 `page_number` 用于保存“`page``number`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: One-based page location when available.
    page_number: int | None
    # 中文：变量 `token_count` 用于保存“词元`count`”相关数据；其精确定义与约束见下方英文说明。
    # English: Deterministic token estimate.
    token_count: int
    # 中文：变量 `protected` 用于保存“`protected`”相关数据；其精确定义与约束见下方英文说明。
    # English: Whether internal splitting should be avoided unless the hard maximum
    #   requires it.
    protected: bool = False
    # 中文：变量 `section_number` 保存条款、章节、步骤或列表的原始编号。
    # English: Original clause, chapter, step, or list identifier.
    section_number: str | None = None
    # 中文：变量 `retrieval_text` 将标题路径和编号注入检索但不污染展示正文。
    # English: Retrieval text injects headings and identifiers without changing display text.
    retrieval_text: str = ""
    # 中文：变量 `source_start_offset` 是清洗后规范文本中的起始字符位置。
    # English: Start character offset in the normalized cleaned document.
    source_start_offset: int = 0
    # 中文：变量 `source_end_offset` 是清洗后规范文本中的结束字符位置。
    # English: End character offset in the normalized cleaned document.
    source_end_offset: int = 0


class StructureParser:
    """中文：该类用于表示或实现“结构解析器（StructureParser）”的职责。

    English: Restore heading hierarchy and create sentence-level chunking units.
    """

    def parse(self, document: CleanedDocument) -> tuple[StructuredUnit, ...]:
        """中文：该函数或方法负责“解析”相关处理。

        English: Return ordered units suitable for deterministic semantic chunking.
        """

        # 中文：变量 `heading_stack` 用于保存“`heading``stack`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Mutable heading stack stores the current hierarchy during the linear
        #   scan.
        heading_stack: list[str] = []
        # 中文：变量 `units` 用于保存“`units`”相关数据；其精确定义与约束见下方英文说明。
        # English: Final units preserve exact document order.
        units: list[StructuredUnit] = []
        # 中文：变量 `source_offset` 在分页块之间加入一个逻辑换行，生成稳定偏移。
        # English: Source offset includes one logical newline between blocks for stable spans.
        source_offset = 0
        for block in document.blocks:
            if block.kind == "heading":
                # 中文：变量 `level` 用于保存“`level`”相关数据；
                # 其精确定义与约束见下方英文说明。
                # English: Missing heading depth safely defaults to top level.
                level = max(1, block.heading_level or 1)
                # 中文：变量 `heading_stack` 用于保存“`heading``stack`”相关数据；
                # 其精确定义与约束见下方英文说明。
                # English: Stack truncation removes headings outside the new section.
                heading_stack = heading_stack[: level - 1]
                heading_stack.append(block.text)
                heading_text = block.text.strip()
                units.append(
                    StructuredUnit(
                        text=heading_text,
                        kind="heading",
                        heading_path=tuple(heading_stack),
                        page_number=block.page_number,
                        token_count=estimate_tokens(heading_text),
                        protected=True,
                        section_number=self._extract_section_number(heading_text),
                        retrieval_text=" > ".join(heading_stack),
                        source_start_offset=source_offset,
                        source_end_offset=source_offset + len(block.text),
                    )
                )
                source_offset += len(block.text) + 1
                continue
            # 中文：变量 `protected` 用于保存“`protected`”相关数据；
            # 其精确定义与约束见下方英文说明。
            # English: Tables and code blocks retain internal structure as protected units.
            protected = block.kind in {"table", "code"}
            # 中文：变量 `parts` 用于保存“`parts`”相关数据；其精确定义与约束见下方英文说明。
            # English: Ordinary prose is split at sentence boundaries to expose semantic
            #   break choices.
            parts = (block.text,) if protected else _split_prose(block.text)
            # 中文：变量 `search_from` 保证重复句子也能获得单调递增的字符偏移。
            # English: Search cursor gives repeated sentences monotonically increasing offsets.
            search_from = 0
            for part in parts:
                local_start = block.text.find(part, search_from)
                local_start = max(0, local_start)
                local_end = local_start + len(part)
                search_from = local_end
                section_number = self._extract_section_number(part)
                unit_kind = self._classify_kind(part, block.kind)
                heading_prefix = " > ".join(heading_stack)
                retrieval_text = " ".join(
                    value for value in (heading_prefix, section_number or "", part) if value
                )
                units.append(
                    StructuredUnit(
                        text=part,
                        kind=unit_kind,
                        heading_path=tuple(heading_stack),
                        page_number=block.page_number,
                        token_count=estimate_tokens(part),
                        protected=protected or unit_kind in {"numbered_clause", "sub_clause"},
                        section_number=section_number,
                        retrieval_text=retrieval_text,
                        source_start_offset=source_offset + local_start,
                        source_end_offset=source_offset + local_end,
                    )
                )
            source_offset += len(block.text) + 1
        return tuple(units)

    @staticmethod
    def _extract_section_number(text: str) -> str | None:
        """中文：返回单元开头的章节、条款、步骤或列表编号。

        English: Return a leading chapter, clause, step, or list identifier.
        """

        match = _NUMBERED_STRUCTURE.search(text.strip())
        return match.group(0).replace(" ", "") if match else None

    @staticmethod
    def _classify_kind(text: str, original_kind: str) -> str:
        """中文：把通用文本行细分为可复用的编号条款和子项类型。

        English: Refine generic text into reusable numbered-clause and sub-clause kinds.
        """

        stripped = text.strip()
        if re.match(r"^第\s*[零〇一二两三四五六七八九十百千万亿0-9]+\s*条", stripped):
            return "numbered_clause"
        if re.match(
            r"^第\s*[零〇一二两三四五六七八九十百千万亿0-9]+\s*[编章节款]",
            stripped,
        ):
            return "heading"
        if re.match(r"^(?:[（(][一二三四五六七八九十0-9]+[）)]|\d+[.)、])", stripped):
            return "sub_clause"
        return original_kind
