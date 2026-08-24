"""中文：本模块负责实现“索引”相关功能。

English: Define immutable dense, lexical, catalog, and runtime index ports.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from enterprise_rag.domain.models import RetrievalScope


class DenseIndex(Protocol):
    """中文：该类用于表示或实现“稠密向量检索索引（DenseIndex）”的职责。

    English: Search normalized chunk vectors by inner-product similarity.
    """

    @property
    def version_id(self) -> str:
        """中文：该函数或方法负责“版本标识符”相关处理。

        English: Return the immutable index version represented by this instance.
        """

    def search(
        self,
        query_vector: Sequence[float],
        limit: int,
        scope: RetrievalScope,
    ) -> Sequence[tuple[str, float]]:
        """中文：该函数或方法负责“执行一次搜索”相关处理。

        English: Return authorized chunk IDs and similarity scores.
        """


class BM25Index(Protocol):
    """中文：该类用于表示或实现“BM25 关键词检索索引（BM25Index）”的职责。

    English: Search tokenized chunks by BM25 lexical relevance.
    """

    @property
    def version_id(self) -> str:
        """中文：该函数或方法负责“版本标识符”相关处理。

        English: Return the immutable index version represented by this instance.
        """

    def search(
        self,
        query: str,
        limit: int,
        scope: RetrievalScope,
    ) -> Sequence[tuple[str, float]]:
        """中文：该函数或方法负责“执行一次搜索”相关处理。

        English: Return authorized chunk IDs and lexical scores.
        """


class SourceCatalog(Protocol):
    """中文：该类用于表示或实现“资料源目录（SourceCatalog）”的职责。

    English: Expose routable source profiles from one immutable index snapshot.
    """

    @property
    def version_id(self) -> str:
        """中文：该函数或方法负责“版本标识符”相关处理。

        English: Return the immutable index version represented by this instance.
        """

    def profiles(self, scope: RetrievalScope) -> Sequence[dict[str, Any]]:
        """中文：该函数或方法负责“资料源画像”相关处理。

        English: Return only source profiles permitted by the retrieval scope.
        """


class IndexRuntime(Protocol):
    """中文：该类用于表示或实现“索引运行时（IndexRuntime）”的职责。

    English: Pin and cache a complete immutable index bundle for online retrieval.
    """

    def active_version_id(self, tenant_id: str) -> str:
        """中文：该函数或方法负责“活动版本标识符”相关处理。

        English: Return the database-selected active index version.
        """

    def dense(self, tenant_id: str, index_version_id: str) -> DenseIndex:
        """中文：该函数或方法负责“稠密向量检索”相关处理。

        English: Return the dense component for an exact immutable version.
        """

    def bm25(self, tenant_id: str, index_version_id: str) -> BM25Index:
        """中文：该函数或方法负责“BM25 关键词检索”相关处理。

        English: Return the lexical component for an exact immutable version.
        """

    def source_catalog(self, tenant_id: str, index_version_id: str) -> SourceCatalog:
        """中文：该函数或方法负责“资料源目录”相关处理。

        English: Return the source catalog for an exact immutable version.
        """
