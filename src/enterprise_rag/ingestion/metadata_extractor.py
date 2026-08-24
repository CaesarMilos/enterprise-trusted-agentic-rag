"""中文：本模块负责实现“元数据提取器”相关功能。

English: Extract safe document and source-profile metadata from prepared content.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from enterprise_rag.domain.models import Chunk

# 中文：变量 `_PROFILE_TERM_PATTERN` 用于保存“资料源画像`term``pattern`”相关数据；
# 其精确定义与约束见下方英文说明。
# English: Profile terms exclude one-character Latin fragments while retaining Chinese
#   characters.
_PROFILE_TERM_PATTERN = re.compile(r"[\u3400-\u9fff]|[A-Za-z][A-Za-z0-9_-]{1,}")


@dataclass(frozen=True, slots=True)
class ExtractedMetadata:
    """中文：该类用于表示或实现“已提取的元数据（ExtractedMetadata）”的职责。

    English: Describe safe searchable metadata produced during ingestion.
    """

    # 中文：变量 `title` 用于保存“标题”相关数据；其精确定义与约束见下方英文说明。
    # English: Best available document title.
    title: str
    # 中文：变量 `media_type` 用于保存“`media``type`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Verified document type.
    media_type: str
    # 中文：变量 `chunk_count` 用于保存“文本块`count`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Total deterministic chunk count.
    chunk_count: int
    # 中文：变量 `token_count` 用于保存“词元`count`”相关数据；其精确定义与约束见下方英文说明。
    # English: Sum of chunk token estimates.
    token_count: int
    # 中文：变量 `profile_terms` 用于保存“资料源画像`terms`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Frequent normalized terms useful for a lightweight source profile.
    profile_terms: tuple[str, ...]


class MetadataExtractor:
    """中文：该类用于表示或实现“元数据提取器（MetadataExtractor）”的职责。

    English: Create deterministic metadata without sending document text to a model.
    """

    def extract(
        self,
        filename: str,
        media_type: str,
        chunks: tuple[Chunk, ...],
    ) -> ExtractedMetadata:
        """中文：该函数或方法负责“提取”相关处理。

        English: Derive title, counts, and frequent profile terms from prepared chunks.
        """

        # 中文：变量 `first_heading` 用于保存“第一项`heading`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: First heading is generally more meaningful than the original filename.
        first_heading = next(
            (chunk.heading_path[-1] for chunk in chunks if chunk.heading_path),
            None,
        )
        # 中文：变量 `fallback_title` 用于保存“`fallback`标题”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Filename suffix is removed only for the fallback display title.
        fallback_title = filename.rsplit(".", maxsplit=1)[0] or filename
        # 中文：变量 `term_counts` 用于保存“`term``counts`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Term counts are deterministic and capped to avoid bloated catalogs.
        term_counts = Counter(
            term.lower() for chunk in chunks for term in _PROFILE_TERM_PATTERN.findall(chunk.text)
        )
        profile_terms = tuple(
            term
            for term, _ in sorted(
                term_counts.items(),
                key=lambda item: (-item[1], item[0]),
            )[:24]
        )
        return ExtractedMetadata(
            title=first_heading or fallback_title,
            media_type=media_type,
            chunk_count=len(chunks),
            token_count=sum(chunk.token_count for chunk in chunks),
            profile_terms=profile_terms,
        )
