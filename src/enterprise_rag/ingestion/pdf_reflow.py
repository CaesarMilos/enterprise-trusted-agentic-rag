"""中文：本模块恢复PDF文本层中的视觉断行、孤立标点、列表编号和重复页眉页脚。

English: Restore visual PDF line wraps, isolated punctuation, list markers, and repeated
headers or footers before structural parsing.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from enterprise_rag.ingestion.loaders.base import RawBlock

# 中文：句末标点阻止普通行与下一行被错误拼接。
# English: Terminal punctuation prevents ordinary lines from being joined with the next line.
_TERMINAL = re.compile(r"[。！？!?；;：:]$|[.!?][\"'”’）)]?$")
# 中文：强结构行在清洗阶段必须保持独立，以便后续解析器识别。
# English: Strong structure lines remain separate so the structure parser can classify them.
_STRUCTURE = re.compile(
    r"^(?:#{1,6}\s*|第\s*[零〇一二两三四五六七八九十百千万亿0-9]+\s*[章节条款步]|"
    r"[（(][一二三四五六七八九十0-9]+[）)]|"
    r"(?:步骤|警告|危险|注意|重要|故障|错误码|参数|规格)\s*[:：]?|"
    r"\d+(?:\.\d+)*[.)、]\s*)",
    re.I,
)
# 中文：孤立列表符号与标点需要附着到相邻正文而不是成为独立语义单元。
# English: Isolated list markers and punctuation attach to adjacent content instead of
# becoming standalone semantic units.
_ISOLATED_PREFIX = re.compile(r"^(?:[（(]\s*[一二三四五六七八九十0-9]+\s*[）)]|[（(]|\d+[.)、])$")
_ISOLATED_SUFFIX = re.compile(r"^[）)；;，,、。.：:]$")


@dataclass(frozen=True, slots=True)
class PDFReflowStats:
    """中文：保存PDF版式恢复的确定性统计数据。

    English: Store deterministic statistics describing PDF text reflow.
    """

    original_lines: int
    output_lines: int
    joined_lines: int
    removed_margin_lines: int
    repaired_markers: int


@dataclass(frozen=True, slots=True)
class PDFReflowResult:
    """中文：保存恢复后的分页文本块和质量统计。

    English: Store reflowed page blocks and quality statistics.
    """

    blocks: tuple[RawBlock, ...]
    stats: PDFReflowStats


class PDFTextReflow:
    """中文：按页恢复PDF视觉布局，同时保留物理页定位。

    English: Restore visual PDF layout page by page while preserving physical locations.
    """

    def reflow(self, blocks: tuple[RawBlock, ...]) -> PDFReflowResult:
        """中文：删除重复页边文本并合并明显属于同一句的视觉断行。

        English: Remove repeated margin text and join visual wraps that clearly belong to
        the same sentence.
        """

        page_lines = [
            tuple(line.strip() for line in block.text.splitlines() if line.strip())
            for block in blocks
        ]
        margins = self._detect_repeated_margins(page_lines)
        output: list[RawBlock] = []
        original_lines = sum(len(lines) for lines in page_lines)
        joined_lines = 0
        removed_margin_lines = 0
        repaired_markers = 0
        for block, lines in zip(blocks, page_lines, strict=True):
            filtered: list[str] = []
            for line in lines:
                if self._margin_key(line) in margins:
                    removed_margin_lines += 1
                    continue
                filtered.append(line)
            repaired, joined, markers = self._repair_page_lines(filtered)
            joined_lines += joined
            repaired_markers += markers
            text = "\n".join(repaired).strip()
            if text:
                output.append(
                    RawBlock(
                        text=text,
                        kind=block.kind,
                        page_number=block.page_number,
                        heading_level=block.heading_level,
                        metadata={**block.metadata, "pdf_reflow_applied": True},
                    )
                )
        return PDFReflowResult(
            tuple(output),
            PDFReflowStats(
                original_lines=original_lines,
                output_lines=sum(len(block.text.splitlines()) for block in output),
                joined_lines=joined_lines,
                removed_margin_lines=removed_margin_lines,
                repaired_markers=repaired_markers,
            ),
        )

    def _detect_repeated_margins(self, pages: list[tuple[str, ...]]) -> frozenset[str]:
        """中文：仅把跨多数页面重复出现的短首尾行识别为页眉页脚。

        English: Treat only short first or last lines repeated across most pages as margins.
        """

        if len(pages) < 3:
            return frozenset()
        candidates: Counter[str] = Counter()
        for lines in pages:
            for line in (*lines[:2], *lines[-2:]):
                key = self._margin_key(line)
                if key and len(key) <= 80:
                    candidates[key] += 1
        threshold = max(3, int(len(pages) * 0.6 + 0.999))
        return frozenset(key for key, count in candidates.items() if count >= threshold)

    @staticmethod
    def _margin_key(line: str) -> str:
        """中文：移除动态页码后生成稳定页边文本比较键。

        English: Remove dynamic page numbers and create a stable margin comparison key.
        """

        compact = re.sub(r"\s+", " ", line).strip().lower()
        return re.sub(r"(?:^|\s)[-—]?\s*\d+\s*[-—]?(?:\s|$)", " # ", compact).strip()

    def _repair_page_lines(self, lines: list[str]) -> tuple[tuple[str, ...], int, int]:
        """中文：恢复孤立列表符号，并按确定性规则合并视觉断行。

        English: Repair isolated list markers and join visual wraps with deterministic rules.
        """

        output: list[str] = []
        pending_prefix = ""
        joined = 0
        markers = 0
        for line in lines:
            if _ISOLATED_PREFIX.fullmatch(line):
                pending_prefix += line.replace(" ", "")
                markers += 1
                continue
            if pending_prefix:
                line = f"{pending_prefix}{line}"
                pending_prefix = ""
            if _ISOLATED_SUFFIX.fullmatch(line) and output:
                output[-1] += line
                markers += 1
                continue
            if output and self._should_join(output[-1], line):
                separator = " " if self._needs_space(output[-1], line) else ""
                output[-1] = f"{output[-1]}{separator}{line}"
                joined += 1
            else:
                output.append(line)
        if pending_prefix:
            output.append(pending_prefix)
        return tuple(output), joined, markers

    @staticmethod
    def _should_join(previous: str, current: str) -> bool:
        """中文：判断当前行是否只是上一行的视觉延续。

        English: Return whether the current line is only a visual continuation of the prior line.
        """

        if not previous or not current or _TERMINAL.search(previous):
            return False
        # 中文：新结构行必须独立；结构编号后的普通正文则应与编号合并。
        # English: A new structural line stays separate, while body text following a structural
        # identifier should join that identifier.
        if _STRUCTURE.search(current):
            return False
        # 中文：短行更可能是页码、标签或真实标题，除非它本身是已识别的结构编号。
        # English: Very short lines are more likely labels or headings unless they are a known
        # structural identifier.
        if len(previous) <= 3 and not _STRUCTURE.search(previous):
            return False
        if len(current) <= 1 and not _ISOLATED_SUFFIX.fullmatch(current):
            return False
        return True

    @staticmethod
    def _needs_space(previous: str, current: str) -> bool:
        """中文：仅在拉丁字母或数字断行之间插入空格。

        English: Insert a space only between wrapped Latin or numeric tokens.
        """

        return previous[-1:].isascii() and current[:1].isascii() and previous[-1:].isalnum()
