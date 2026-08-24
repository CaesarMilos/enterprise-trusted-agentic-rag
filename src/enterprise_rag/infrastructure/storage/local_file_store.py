"""中文：本模块负责实现“本地文件存储”相关功能。

English: Persist original document bytes in tenant-isolated local directories.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import BinaryIO

from enterprise_rag.core.enums import ErrorCategory
from enterprise_rag.core.exceptions import StorageError, error_detail
from enterprise_rag.domain.protocols.storage import StoredFile
from enterprise_rag.infrastructure.storage.file_store import (
    ensure_within_root,
    safe_segment,
    sanitized_extension,
)

# 中文：变量 `_COPY_BUFFER_SIZE` 用于保存“`copy``buffer``size`”相关数据；
# 其精确定义与约束见下方英文说明。
# English: Stream copy buffer balances memory use and filesystem throughput.
_COPY_BUFFER_SIZE = 1024 * 1024


class LocalFileStore:
    """中文：该类用于表示或实现“本地文件存储（LocalFileStore）”的职责。

    English: Implement atomic local file storage using opaque version-derived keys.
    """

    def __init__(self, root: Path) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store and create the configured upload root.
        """

        # 中文：变量 `_root` 用于保存“`root`”相关数据；其精确定义与约束见下方英文说明。
        # English: Canonical root is used for every containment check.
        self._root = root.expanduser().resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        tenant_id: str,
        document_version_id: str,
        filename: str,
        source: BinaryIO,
    ) -> StoredFile:
        """中文：该函数或方法负责“保存目标对象”相关处理。

        English: Stream bytes to a temporary file, fsync them, and atomically publish the
        result.
        """

        # 中文：变量 `safe_tenant` 用于保存“安全租户”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Validated identifiers become opaque directory and filename segments.
        safe_tenant = safe_segment(tenant_id, "tenant_id")
        safe_version = safe_segment(document_version_id, "document_version_id")
        # 中文：变量 `extension` 用于保存“`extension`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Extension is cosmetic and never determines parser selection by itself.
        extension = sanitized_extension(filename)
        # 中文：变量 `storage_key` 用于保存“存储`key`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Storage key is relative and contains no caller-controlled base filename.
        storage_key = f"{safe_version}/original.{extension}"
        # 中文：变量 `tenant_root` 用于保存“租户`root`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Tenant root enforces physical separation between organizations.
        tenant_root = ensure_within_root(self._root / safe_tenant, self._root)
        # 中文：变量 `destination` 用于保存“`destination`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Final destination remains beneath both global and tenant roots.
        destination = ensure_within_root(tenant_root / storage_key, tenant_root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        # 中文：变量 `digest` 用于保存“`digest`”相关数据；其精确定义与约束见下方英文说明。
        # English: Running digest avoids reading the finished file a second time.
        digest = hashlib.sha256()
        # 中文：变量 `size_bytes` 用于保存“`size``bytes`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Byte count is checked and recorded during the same streaming pass.
        size_bytes = 0
        # 中文：变量 `temporary_path` 用于保存“`temporary``path`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Temporary file lives beside the destination so os.replace remains atomic.
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=destination.parent,
                prefix=".upload-",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                while True:
                    # 中文：变量 `block` 用于保存“`block`”相关数据；
                    # 其精确定义与约束见下方英文说明。
                    # English: Current input block is bounded by the fixed copy buffer.
                    block = source.read(_COPY_BUFFER_SIZE)
                    if not block:
                        break
                    temporary.write(block)
                    digest.update(block)
                    size_bytes += len(block)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, destination)
        except OSError as exc:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise StorageError(
                error_detail(
                    "FILE_SAVE_FAILED",
                    ErrorCategory.STORAGE,
                    "The original document could not be saved.",
                )
            ) from exc
        return StoredFile(
            storage_key=storage_key,
            content_hash=digest.hexdigest(),
            size_bytes=size_bytes,
        )

    def open(self, tenant_id: str, storage_key: str) -> BinaryIO:
        """中文：该函数或方法负责“打开目标对象”相关处理。

        English: Open a tenant-owned file for binary reading.
        """

        # 中文：变量 `path` 用于保存“`path`”相关数据；其精确定义与约束见下方英文说明。
        # English: Materialized path performs every segment and containment check.
        path = self.materialized_path(tenant_id, storage_key)
        try:
            return path.open("rb")
        except OSError as exc:
            raise StorageError(
                error_detail(
                    "FILE_OPEN_FAILED",
                    ErrorCategory.STORAGE,
                    "The stored original document could not be opened.",
                )
            ) from exc

    def materialized_path(self, tenant_id: str, storage_key: str) -> Path:
        """中文：该函数或方法负责“已物化的路径”相关处理。

        English: Resolve an opaque storage key to a contained local path.
        """

        # 中文：变量 `safe_tenant` 用于保存“安全租户”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Tenant identifier is the only direct root segment.
        safe_tenant = safe_segment(tenant_id, "tenant_id")
        # 中文：变量 `key_parts` 用于保存“`key``parts`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Storage keys are split and independently validated to reject traversal.
        key_parts = tuple(part for part in storage_key.replace("\\", "/").split("/") if part)
        if not key_parts:
            raise StorageError(
                error_detail(
                    "EMPTY_STORAGE_KEY",
                    ErrorCategory.STORAGE,
                    "The storage key is empty.",
                )
            )
        # 中文：变量 `safe_parts` 用于保存“安全`parts`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Validated parts are safe opaque segments, not a caller-controlled path.
        safe_parts = tuple(safe_segment(part, "storage_key") for part in key_parts)
        tenant_root = ensure_within_root(self._root / safe_tenant, self._root)
        return ensure_within_root(tenant_root.joinpath(*safe_parts), tenant_root)

    def delete(self, tenant_id: str, storage_key: str) -> None:
        """中文：该函数或方法负责“删除目标对象”相关处理。

        English: Delete a tenant-owned file while leaving unrelated files untouched.
        """

        # 中文：变量 `path` 用于保存“`path`”相关数据；其精确定义与约束见下方英文说明。
        # English: Exact contained target prevents broad or recursive deletion.
        path = self.materialized_path(tenant_id, storage_key)
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            raise StorageError(
                error_detail(
                    "FILE_DELETE_FAILED",
                    ErrorCategory.STORAGE,
                    "The stored original document could not be deleted.",
                )
            ) from exc
