"""中文：本模块负责实现“索引协调器”相关功能。

English: Coordinate staging, reload validation, atomic publication, and database activation.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from pathlib import Path

from enterprise_rag.core.enums import ErrorCategory
from enterprise_rag.core.exceptions import EnterpriseRAGError, IndexBuildError, error_detail
from enterprise_rag.indexing.bm25_index import BM25IndexBuilder, PersistentBM25Index
from enterprise_rag.indexing.embedding_service import EmbeddingService
from enterprise_rag.indexing.index_manifest import (
    create_manifest,
    load_manifest,
    save_manifest,
    verify_manifest,
)
from enterprise_rag.indexing.models import IndexBuildPlan
from enterprise_rag.indexing.source_catalog import PersistentSourceCatalog, SourceCatalogBuilder
from enterprise_rag.indexing.vector_index import FaissVectorIndex, VectorIndexBuilder


class IndexCoordinator:
    """中文：该类用于表示或实现“索引协调器（IndexCoordinator）”的职责。

    English: Build every index component from one plan and publish only after reload validation.
    """

    def __init__(
        self,
        index_root: Path,
        embedding_service: EmbeddingService,
        vector_builder: VectorIndexBuilder,
        bm25_builder: BM25IndexBuilder,
        catalog_builder: SourceCatalogBuilder,
    ) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store the snapshot root and stateless component builders.
        """

        # 中文：变量 `_index_root` 用于保存“索引`root`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Canonical root contains tenant-isolated staging and published snapshots.
        self._index_root = index_root.expanduser().resolve()
        # 中文：变量 `_embedding_service` 用于保存“向量嵌入服务”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Service supplies normalized aligned vectors.
        self._embedding_service = embedding_service
        # 中文：变量 `_vector_builder` 用于保存“向量构建器”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Dense component builder writes FAISS and mapping artifacts.
        self._vector_builder = vector_builder
        # 中文：变量 `_bm25_builder` 用于保存“BM25 关键词检索构建器”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Lexical component builder writes the BM25 corpus.
        self._bm25_builder = bm25_builder
        # 中文：变量 `_catalog_builder` 用于保存“目录构建器”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Routing catalog builder writes source profiles.
        self._catalog_builder = catalog_builder

    def build_and_publish(
        self,
        plan: IndexBuildPlan,
        activate: Callable[[str], str | None],
    ) -> str | None:
        """中文：该函数或方法负责“构建并且发布”相关处理。

        English: Publish a validated immutable snapshot and invoke transactional database
        activation.
        """

        # 中文：此处调用 `_validate_segment` 以执行“校验`segment`”相关步骤；
        # 具体约束见下方英文说明。
        # English: Tenant and version identifiers are validated as opaque safe segments.
        _validate_segment(plan.tenant_id)
        _validate_segment(plan.index_version_id)
        # 中文：变量 `tenant_root` 用于保存“租户`root`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Tenant root physically separates customer index artifacts.
        tenant_root = self._index_root / plan.tenant_id
        # 中文：变量 `staging` 用于保存“`staging`”相关数据；其精确定义与约束见下方英文说明。
        # English: Staging suffix prevents incomplete snapshots from appearing published.
        staging = tenant_root / f"{plan.index_version_id}.staging"
        # 中文：变量 `published` 用于保存“`published`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Published directory name is exactly the immutable index version ID.
        published = tenant_root / plan.index_version_id
        if staging.exists() or published.exists():
            raise IndexBuildError(
                error_detail(
                    "INDEX_VERSION_EXISTS",
                    ErrorCategory.INDEX,
                    "The target immutable index version already exists.",
                )
            )
        staging.mkdir(parents=True, exist_ok=False)
        try:
            # 中文：变量 `vectors` 用于保存“`vectors`”相关数据；
            # 其精确定义与约束见下方英文说明。
            # English: Dense and lexical components consume the exact same ordered plan
            #   entries.
            vectors = self._embedding_service.embed(tuple(entry.text for entry in plan.entries))
            artifacts = self._vector_builder.build(plan, vectors, staging)
            artifacts += self._bm25_builder.build(plan, staging)
            artifacts += self._catalog_builder.build(plan, staging)
            # 中文：变量 `manifest` 用于保存“清单”相关数据；其精确定义与约束见下方英文说明。
            # English: Manifest checksums cover every component artifact.
            manifest = create_manifest(plan, artifacts)
            save_manifest(manifest, staging)
            # 中文：本注释说明当前代码步骤的用途、约束或设计原因。
            # English: Fresh process-like reload validates serialization, counts,
            #   versions, and checksums.
            self._validate_reloaded(plan, staging)
            # 中文：本步骤涉及快照，具体约束见下方英文说明。
            # English: Same-filesystem replace atomically makes the complete snapshot
            #   discoverable.
            os.replace(staging, published)
            try:
                # 中文：变量 `previous_version_id` 用于保存“`previous`版本标识符”相关数据；
                # 其精确定义与约束见下方英文说明。
                # English: Database transaction selects ACTIVE only after filesystem
                #   publication.
                previous_version_id = activate(plan.index_version_id)
            except Exception:
                # 中文：变量 `raise` 用于保存“`raise`”相关数据；
                # 其精确定义与约束见下方英文说明。
                # English: Published but inactive snapshot remains recoverable; old ACTIVE
                #   continues serving.
                raise
            return previous_version_id
        except Exception as exc:
            if staging.exists():
                # 中文：本步骤涉及目录、安全，具体约束见下方英文说明。
                # English: Exact staging directory is safe to remove because it was
                #   created in this call.
                shutil.rmtree(staging)
            # 中文：租约丢失和过期计划等领域冲突保留原始稳定错误码。
            # English: Domain conflicts such as lease loss and stale plans retain their
            # original stable error codes instead of becoming generic index failures.
            if isinstance(exc, EnterpriseRAGError):
                raise
            raise IndexBuildError(
                error_detail(
                    "INDEX_BUILD_FAILED",
                    ErrorCategory.INDEX,
                    "The new index snapshot failed before activation.",
                    reason=str(exc),
                )
            ) from exc

    @staticmethod
    def _validate_reloaded(plan: IndexBuildPlan, staging: Path) -> None:
        """中文：该内部函数负责“校验重新加载的”相关处理。

        English: Reload every staged component and verify version and entry-set consistency.
        """

        # 中文：变量 `manifest` 用于保存“清单”相关数据；其精确定义与约束见下方英文说明。
        # English: Manifest validates every component's raw bytes.
        manifest = load_manifest(staging)
        verify_manifest(staging, manifest)
        # 中文：变量 `dense` 用于保存“稠密向量检索”相关数据；其精确定义与约束见下方英文说明。
        # English: Independent reload catches serialization and provider-library
        #   incompatibilities.
        dense = FaissVectorIndex.load(staging)
        bm25 = PersistentBM25Index.load(staging)
        catalog = PersistentSourceCatalog.load(staging)
        if not (
            dense.version_id
            == bm25.version_id
            == catalog.version_id
            == manifest.index_version_id
            == plan.index_version_id
        ):
            raise ValueError("staged index component versions differ")
        if manifest.chunk_ids != tuple(entry.chunk_id for entry in plan.entries):
            raise ValueError("staged manifest chunk IDs differ from build plan")


def _validate_segment(value: str) -> None:
    """中文：该内部函数负责“校验路径段”相关处理。

    English: Reject index path segments containing traversal or separator characters.
    """

    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise ValueError("index path segment is unsafe")
