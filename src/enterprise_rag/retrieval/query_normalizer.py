"""中文：本模块负责实现“查询规范化器”相关功能。

English: Normalize search text deterministically without changing the user's intent.
"""

from __future__ import annotations

import re
import unicodedata

from enterprise_rag.retrieval.identifier_normalizer import normalize_identifiers

# 中文：变量 `_WHITESPACE` 用于保存“`whitespace`”相关数据；其精确定义与约束见下方英文说明。
# English: Repeated whitespace has no lexical or embedding value.
_WHITESPACE = re.compile(r"\s+")


class QueryNormalizer:
    """中文：该类用于表示或实现“查询规范化器（QueryNormalizer）”的职责。

    English: Apply stable Unicode and whitespace normalization only.
    """

    def normalize(self, query: str) -> str:
        """中文：该函数或方法负责“规范化”相关处理。

        English: Return a stripped NFKC query and reject an empty result.
        """

        # 中文：变量 `normalized` 用于保存“`normalized`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: NFKC aligns compatibility characters with indexed document cleaning.
        normalized = unicodedata.normalize("NFKC", query)
        normalized = _WHITESPACE.sub(" ", normalized).strip()
        if not normalized:
            raise ValueError("query must contain non-whitespace text")
        return normalize_identifiers(normalized).text
