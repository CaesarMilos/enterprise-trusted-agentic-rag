"""中文：本模块为 Dense、BM25 和引用构造彼此独立的确定性文本通道。

English: Build separate deterministic text channels for dense, BM25, and citation use.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from enterprise_rag.core.ids import content_sha256
from enterprise_rag.domain.models import Chunk

# 中文：索引裁剪按字符跨度保留中英文词元，不会截断 UTF-8 字节。
# English: Index truncation preserves character spans for CJK and Latin tokens without cutting
# UTF-8 bytes.
_TOKEN_SPAN_PATTERN = re.compile(r"[\u3400-\u9fff]|[A-Za-z0-9_]+|[^\s]")


@dataclass(frozen=True, slots=True)
class IndexTextPayload:
    """中文：保存一个 Chunk 的 Dense、词法及审计文本派生结果。

    English: Store dense, lexical, and audit text derivatives for one chunk.
    """

    # 中文：关键变量 `embedding_text` 是有界且不重复的向量模型输入。
    # English: Key variable `embedding_text` is the bounded non-repeated embedding input.
    embedding_text: str
    # 中文：关键变量 `lexical_text` 保留完整正文供 BM25 使用。
    # English: Key variable `lexical_text` retains the complete body for BM25.
    lexical_text: str
    # 中文：变量 `context_header` 仅包含去重后的紧凑结构元数据。
    # English: Variable `context_header` contains only deduplicated compact structure metadata.
    context_header: str
    # 中文：正文指纹用于区分真实重复内容与向量塌缩。
    # English: Body fingerprint distinguishes true duplicates from vector collapse.
    content_fingerprint: str


class IndexTextBuilder:
    """中文：以正文优先预算构建无重复标题污染的索引文本。

    English: Build body-prioritized index text without repeated-heading contamination.
    """

    strategy_version = "index-text-v5.1"

    def __init__(
        self,
        embedding_max_tokens: int = 384,
        max_heading_depth: int = 2,
        max_heading_characters: int = 96,
    ) -> None:
        """中文：校验并保存 Dense 文本和标题元数据预算。

        English: Validate and store dense-text and heading-metadata budgets.
        """

        if embedding_max_tokens < 32:
            raise ValueError("embedding text budget must be at least 32 tokens")
        if max_heading_depth < 0 or max_heading_characters < 1:
            raise ValueError("heading limits must be nonnegative and nonzero")
        self._embedding_max_tokens = embedding_max_tokens
        self._max_heading_depth = max_heading_depth
        self._max_heading_characters = max_heading_characters

    def build(self, chunk: Chunk) -> IndexTextPayload:
        """中文：从可引用正文构造紧凑头部、Dense 文本和完整词法文本。

        English: Derive a compact header, dense text, and full lexical text from citable body.
        """

        # 中文：关键变量 `body` 只取原始可引用正文，避免继承旧 retrieval_text 的重复前缀。
        # English: Key variable `body` uses only citable source text, avoiding legacy repeated
        # retrieval prefixes.
        body = self._normalize_spacing(chunk.body_text)
        context_header = self._context_header(chunk)
        lexical_text = "\n".join(value for value in (context_header, body) if value)
        embedding_text = self._truncate_head_tail(lexical_text)
        return IndexTextPayload(
            embedding_text=embedding_text,
            lexical_text=lexical_text,
            context_header=context_header,
            content_fingerprint=content_sha256(body),
        )

    def _context_header(self, chunk: Chunk) -> str:
        """中文：构造最多两层去重标题和一个结构编号的紧凑头部。

        English: Build a compact header with bounded unique headings and one section anchor.
        """

        unique_headings: list[str] = []
        for heading in chunk.heading_path[-self._max_heading_depth :]:
            compact = self._normalize_spacing(heading)[: self._max_heading_characters]
            if compact and compact not in unique_headings and compact not in chunk.body_text[:160]:
                unique_headings.append(compact)
        header_parts: list[str] = []
        if unique_headings:
            header_parts.append(f"[层级 / Heading] {' / '.join(unique_headings)}")
        if chunk.section_number and chunk.section_number not in chunk.body_text[:80]:
            header_parts.append(f"[编号 / Section] {chunk.section_number}")
        return "\n".join(header_parts)

    def _truncate_head_tail(self, text: str) -> str:
        """中文：超预算时保留正文首尾，降低只截取共同前缀导致的向量碰撞。

        English: Preserve both head and tail when over budget to reduce common-prefix collapse.
        """

        matches = tuple(_TOKEN_SPAN_PATTERN.finditer(text))
        if len(matches) <= self._embedding_max_tokens:
            return text
        # 中文：变量 `head_budget` 略偏向开头以保留法条号、主体和主要规则。
        # English: Variable `head_budget` favors the start to preserve anchors and main rules.
        head_budget = (self._embedding_max_tokens * 2) // 3
        tail_budget = self._embedding_max_tokens - head_budget
        head_end = matches[head_budget - 1].end()
        tail_start = matches[-tail_budget].start()
        return f"{text[:head_end].rstrip()}\n[… / omitted …]\n{text[tail_start:].lstrip()}"

    @staticmethod
    def _normalize_spacing(text: str) -> str:
        """中文：压缩水平空白但保留段落换行，生成稳定索引文本。

        English: Collapse horizontal whitespace while preserving paragraph lines.
        """

        lines = (re.sub(r"[\t \u3000]+", " ", line).strip() for line in text.splitlines())
        return "\n".join(line for line in lines if line)
