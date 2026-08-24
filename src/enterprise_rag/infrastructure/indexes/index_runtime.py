"""中文：本模块负责实现“索引运行时”相关功能。

English: Load and cache complete immutable index bundles with thread-safe version pinning.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

from enterprise_rag.indexing.bm25_index import PersistentBM25Index
from enterprise_rag.indexing.index_manifest import load_manifest, verify_manifest
from enterprise_rag.indexing.source_catalog import PersistentSourceCatalog
from enterprise_rag.indexing.vector_index import FaissVectorIndex


@dataclass(frozen=True, slots=True)
class _IndexBundle:
    """中文：该类用于表示或实现“索引集合包（_IndexBundle）”的职责。

    English: Hold all components loaded from one verified immutable snapshot.
    """

    # 中文：变量 `dense` 用于保存“稠密向量检索”相关数据；其精确定义与约束见下方英文说明。
    # English: Dense FAISS component.
    dense: FaissVectorIndex
    # 中文：变量 `bm25` 用于保存“BM25 关键词检索”相关数据；其精确定义与约束见下方英文说明。
    # English: Lexical BM25 component.
    bm25: PersistentBM25Index
    # 中文：变量 `catalog` 用于保存“目录”相关数据；其精确定义与约束见下方英文说明。
    # English: Source routing catalog.
    catalog: PersistentSourceCatalog


class LocalIndexRuntime:
    """中文：该类用于表示或实现“本地索引运行时（LocalIndexRuntime）”的职责。

    English: Resolve active versions from the database and cache verified local artifacts.
    """

    def __init__(self, root: Path, active_lookup: Callable[[str], str]) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store the canonical index root and database active-version callback.
        """

        # 中文：变量 `_root` 用于保存“`root`”相关数据；其精确定义与约束见下方英文说明。
        # English: Canonical root contains tenant/version snapshot directories.
        self._root = root.expanduser().resolve()
        # 中文：变量 `_active_lookup` 用于保存“活动`lookup`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Callback is the authoritative ACTIVE version selector.
        self._active_lookup = active_lookup
        # 中文：变量 `_cache` 用于保存“`cache`”相关数据；其精确定义与约束见下方英文说明。
        # English: Cache is keyed by tenant and immutable version.
        self._cache: dict[tuple[str, str], _IndexBundle] = {}
        # 中文：变量 `_lock` 用于保存“`lock`”相关数据；其精确定义与约束见下方英文说明。
        # English: Reentrant lock serializes first-load and cache updates.
        self._lock = RLock()

    def active_version_id(self, tenant_id: str) -> str:
        """中文：该函数或方法负责“活动版本标识符”相关处理。

        English: Return the database-selected active index version.
        """

        return self._active_lookup(tenant_id)

    def dense(self, tenant_id: str, index_version_id: str) -> FaissVectorIndex:
        """中文：该函数或方法负责“稠密向量检索”相关处理。

        English: Return the dense component for an exact immutable version.
        """

        return self._bundle(tenant_id, index_version_id).dense

    def bm25(self, tenant_id: str, index_version_id: str) -> PersistentBM25Index:
        """中文：该函数或方法负责“BM25 关键词检索”相关处理。

        English: Return the lexical component for an exact immutable version.
        """

        return self._bundle(tenant_id, index_version_id).bm25

    def source_catalog(
        self,
        tenant_id: str,
        index_version_id: str,
    ) -> PersistentSourceCatalog:
        """中文：该函数或方法负责“资料源目录”相关处理。

        English: Return the source catalog for an exact immutable version.
        """

        return self._bundle(tenant_id, index_version_id).catalog

    def _bundle(self, tenant_id: str, index_version_id: str) -> _IndexBundle:
        """中文：该内部函数负责“集合包”相关处理。

        English: Load, verify, and cache a complete immutable snapshot.
        """

        # 中文：变量 `unsafe_identifier` 用于保存“`unsafe``identifier`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Unsafe segments are rejected before path resolution.
        unsafe_identifier = any(
            value in {"", ".", ".."} or "/" in value or "\\" in value
            for value in (tenant_id, index_version_id)
        )
        if unsafe_identifier:
            raise ValueError("unsafe index runtime identifier")
        # 中文：变量 `key` 用于保存“`key`”相关数据；其精确定义与约束见下方英文说明。
        # English: Cache key retains tenant isolation even for equal version labels.
        key = (tenant_id, index_version_id)
        with self._lock:
            if key in self._cache:
                return self._cache[key]
            # 中文：变量 `directory` 用于保存“目录”相关数据；其精确定义与约束见下方英文说明。
            # English: Snapshot path remains beneath the configured root.
            directory = (self._root / tenant_id / index_version_id).resolve()
            directory.relative_to(self._root)
            # 中文：变量 `manifest` 用于保存“清单”相关数据；其精确定义与约束见下方英文说明。
            # English: Manifest raw-byte validation precedes component loading.
            manifest = load_manifest(directory)
            verify_manifest(directory, manifest)
            if manifest.tenant_id != tenant_id or manifest.index_version_id != index_version_id:
                raise ValueError("index manifest identity does not match requested snapshot")
            bundle = _IndexBundle(
                dense=FaissVectorIndex.load(directory),
                bm25=PersistentBM25Index.load(directory),
                catalog=PersistentSourceCatalog.load(directory),
            )
            self._cache[key] = bundle
            return bundle
