"""中文：本模块负责实现“资料源资料源画像目录”相关功能。

English: Adapt an immutable source catalog to retrieval-specific profile mappings.
"""

from __future__ import annotations

from enterprise_rag.domain.protocols.indexes import SourceCatalog
from enterprise_rag.retrieval.models import RetrievalQuery


class SourceProfileCatalog:
    """中文：该类用于表示或实现“资料源资料源画像目录（SourceProfileCatalog）”的职责。

    English: Read profiles only from the query's pinned index version and ACL scope.
    """

    def __init__(self, catalog: SourceCatalog) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store one immutable catalog component.
        """

        # 中文：变量 `_catalog` 用于保存“目录”相关数据；其精确定义与约束见下方英文说明。
        # English: Catalog version is checked on every query through its scope.
        self._catalog = catalog

    def profiles(self, query: RetrievalQuery) -> tuple[dict[str, object], ...]:
        """中文：该函数或方法负责“资料源画像”相关处理。

        English: Return authorized source profiles for routing.
        """

        return tuple(self._catalog.profiles(query.scope))
