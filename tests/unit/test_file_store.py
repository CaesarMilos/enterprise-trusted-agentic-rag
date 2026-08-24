"""中文：本模块负责实现“测试文件存储”相关功能。

English: Verify tenant isolation, checksums, atomic persistence, and traversal rejection.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from enterprise_rag.core.exceptions import StorageError
from enterprise_rag.core.ids import content_sha256
from enterprise_rag.infrastructure.storage.local_file_store import LocalFileStore


def test_local_file_store_round_trip(tmp_path: Path) -> None:
    """中文：该测试用于验证“本地文件存储轮次往返”相关行为。

    English: Ensure saved bytes can be reopened using only the returned opaque key.
    """

    # 中文：变量 `store` 用于保存“存储”相关数据；其精确定义与约束见下方英文说明。
    # English: Store under an isolated temporary root.
    store = LocalFileStore(tmp_path / "uploads")
    # 中文：变量 `payload` 用于保存“载荷”相关数据；其精确定义与约束见下方英文说明。
    # English: Payload simulates upload bytes without depending on a web framework.
    payload = b"trusted enterprise evidence"

    stored = store.save(
        tenant_id="tenant-a",
        document_version_id="ver_123",
        filename="../../unsafe-name.txt",
        source=io.BytesIO(payload),
    )

    assert stored.content_hash == content_sha256(payload)
    assert stored.size_bytes == len(payload)
    with store.open("tenant-a", stored.storage_key) as persisted:
        assert persisted.read() == payload


def test_local_file_store_rejects_storage_key_traversal(tmp_path: Path) -> None:
    """中文：该测试用于验证“本地文件存储拒绝存储键路径穿越”相关行为。

    English: Ensure an opaque key cannot escape the tenant directory.
    """

    # 中文：变量 `store` 用于保存“存储”相关数据；其精确定义与约束见下方英文说明。
    # English: Store root contains no file; failure must occur during path validation.
    store = LocalFileStore(tmp_path / "uploads")

    with pytest.raises(StorageError):
        store.materialized_path("tenant-a", "../tenant-b/secret.txt")
