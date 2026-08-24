"""中文：本模块负责实现“Markdown加载器”相关功能。

English: Load Markdown while preserving headings, paragraphs, lists, and fenced code.
"""

from __future__ import annotations

import re
from pathlib import Path

from enterprise_rag.ingestion.loaders.base import LoadedDocument, RawBlock
from enterprise_rag.ingestion.loaders.text_loader import TextLoader

# 中文：变量 `_HEADING_PATTERN` 用于保存“`heading``pattern`”相关数据；
# 其精确定义与约束见下方英文说明。
# English: ATX headings are recognized without requiring a Markdown rendering dependency.
_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


class MarkdownLoader:
    """中文：该类用于表示或实现“Markdown加载器（MarkdownLoader）”的职责。

    English: Parse common Markdown block structure in deterministic source order.
    """

    @property
    def media_types(self) -> frozenset[str]:
        """中文：该函数或方法负责“媒体类型”相关处理。

        English: Return Markdown type aliases supported by this loader.
        """

        return frozenset({"md", "markdown"})

    def load(self, path: Path, filename: str, media_type: str) -> LoadedDocument:
        """中文：该函数或方法负责“加载并解析目标数据”相关处理。

        English: Decode Markdown and emit typed blocks without executing embedded content.
        """

        # 中文：变量 `decoded` 用于保存“`decoded`”相关数据；其精确定义与约束见下方英文说明。
        # English: TextLoader supplies deterministic encoding behavior.
        decoded = TextLoader().load(path, filename, "txt")
        # 中文：变量 `lines` 用于保存“`lines`”相关数据；其精确定义与约束见下方英文说明。
        # English: Paragraph rejoin recreates a normalized line stream for block
        #   recognition.
        lines = "\n\n".join(block.text for block in decoded.blocks).splitlines()
        # 中文：变量 `blocks` 用于保存“`blocks`”相关数据；其精确定义与约束见下方英文说明。
        # English: Parsed blocks preserve source order.
        blocks: list[RawBlock] = []
        # 中文：变量 `buffer` 用于保存“`buffer`”相关数据；其精确定义与约束见下方英文说明。
        # English: Buffer accumulates adjacent paragraph or list lines.
        buffer: list[str] = []
        # 中文：变量 `code_buffer` 用于保存“`code``buffer`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Code buffer accumulates fenced code without interpreting it.
        code_buffer: list[str] = []
        # 中文：变量 `in_code` 用于保存“`in``code`”相关数据；其精确定义与约束见下方英文说明。
        # English: Fence state prevents headings inside code blocks from being parsed.
        in_code = False

        def flush_buffer() -> None:
            """中文：该函数或方法负责“刷新缓冲区”相关处理。

            English: Emit and clear the current ordinary-text buffer.
            """

            if buffer:
                blocks.append(RawBlock(text="\n".join(buffer).strip(), kind="paragraph"))
                buffer.clear()

        for line in lines:
            # 中文：变量 `stripped` 用于保存“`stripped`”相关数据；
            # 其精确定义与约束见下方英文说明。
            # English: Stripped line is used only for syntax detection; original line
            #   remains in content.
            stripped = line.strip()
            if stripped.startswith("```"):
                if in_code:
                    blocks.append(RawBlock(text="\n".join(code_buffer), kind="code"))
                    code_buffer.clear()
                    in_code = False
                else:
                    flush_buffer()
                    in_code = True
                continue
            if in_code:
                code_buffer.append(line)
                continue
            # 中文：变量 `heading_match` 用于保存“`heading``match`”相关数据；
            # 其精确定义与约束见下方英文说明。
            # English: Heading match is evaluated only outside fenced code.
            heading_match = _HEADING_PATTERN.match(stripped)
            if heading_match:
                flush_buffer()
                blocks.append(
                    RawBlock(
                        text=heading_match.group(2),
                        kind="heading",
                        heading_level=len(heading_match.group(1)),
                    )
                )
            elif not stripped:
                flush_buffer()
            else:
                buffer.append(line)
        flush_buffer()
        if code_buffer:
            # 中文：本注释说明当前代码步骤的用途、约束或设计原因。
            # English: Unterminated code remains inert content rather than disappearing.
            blocks.append(RawBlock(text="\n".join(code_buffer), kind="code"))
        return LoadedDocument(
            filename=filename,
            media_type=media_type,
            blocks=tuple(blocks),
            metadata={"encoding": decoded.metadata["encoding"], "block_count": len(blocks)},
        )
