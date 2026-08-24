"""中文：本模块负责实现“索引包的公共导出”相关功能。

English: Expose immutable on-disk index runtime loading.
"""

from enterprise_rag.infrastructure.indexes.index_runtime import LocalIndexRuntime

__all__ = ["LocalIndexRuntime"]
