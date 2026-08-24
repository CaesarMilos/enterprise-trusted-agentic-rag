"""中文：本模块负责实现“存储”相关功能。

English: Define tenant-safe original-file storage operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol


@dataclass(frozen=True, slots=True)
class StoredFile:
    """中文：该类用于表示或实现“已存储的文件（StoredFile）”的职责。

    English: Describe bytes persisted under an opaque tenant-isolated storage key.
    """

    # 中文：变量 `storage_key` 用于保存“存储`key`”相关数据；其精确定义与约束见下方英文说明。
    # English: Opaque key understood only by the storage adapter.
    storage_key: str
    # 中文：变量 `content_hash` 用于保存“`content``hash`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: SHA-256 checksum calculated while persisting bytes.
    content_hash: str
    # 中文：变量 `size_bytes` 用于保存“`size``bytes`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Persisted byte length.
    size_bytes: int


class FileStore(Protocol):
    """中文：该类用于表示或实现“文件存储（FileStore）”的职责。

    English: Persist and retrieve files without exposing caller-controlled filesystem paths.
    """

    def save(
        self,
        tenant_id: str,
        document_version_id: str,
        filename: str,
        source: BinaryIO,
    ) -> StoredFile:
        """中文：该函数或方法负责“保存目标对象”相关处理。

        English: Persist a stream and return its opaque key, checksum, and byte length.
        """

    def open(self, tenant_id: str, storage_key: str) -> BinaryIO:
        """中文：该函数或方法负责“打开目标对象”相关处理。

        English: Open a tenant-owned stored file for binary reading.
        """

    def materialized_path(self, tenant_id: str, storage_key: str) -> Path:
        """中文：该函数或方法负责“已物化的路径”相关处理。

        English: Return a safe local path for parsers requiring random access.
        """

    def delete(self, tenant_id: str, storage_key: str) -> None:
        """中文：该函数或方法负责“删除目标对象”相关处理。

        English: Delete a tenant-owned file if it exists.
        """
