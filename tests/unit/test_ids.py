"""中文：本模块负责实现“测试标识符”相关功能。

English: Verify random and deterministic public identifier behavior.
"""

from __future__ import annotations

import pytest

from enterprise_rag.core.exceptions import ValidationError
from enterprise_rag.core.ids import content_sha256, new_id, stable_chunk_id, stable_id


def test_stable_id_is_deterministic_and_order_sensitive() -> None:
    """中文：该测试用于验证“稳定标识符为确定性并且顺序敏感”相关行为。

    English: Ensure identical parts reproduce an ID while reordered parts do not.
    """

    # 中文：变量 `first` 用于保存“第一项”相关数据；其精确定义与约束见下方英文说明。
    # English: First result is the identity baseline.
    first = stable_id("doc", ("tenant-a", "example"))
    # 中文：变量 `repeated` 用于保存“`repeated`”相关数据；其精确定义与约束见下方英文说明。
    # English: Second result verifies repeatability.
    repeated = stable_id("doc", ("tenant-a", "example"))
    # 中文：变量 `reordered` 用于保存“`reordered`”相关数据；其精确定义与约束见下方英文说明。
    # English: Reordered result verifies unambiguous canonicalization.
    reordered = stable_id("doc", ("example", "tenant-a"))

    assert first == repeated
    assert first != reordered


def test_new_id_uses_random_payload() -> None:
    """中文：该测试用于验证“新建标识符使用随机载荷”相关行为。

    English: Ensure independently created entities do not receive the same identifier.
    """

    # 中文：变量 `first` 用于保存“第一项”相关数据；其精确定义与约束见下方英文说明。
    # English: Two random IDs should differ while retaining the requested entity prefix.
    first = new_id("job")
    second = new_id("job")

    assert first.startswith("job_")
    assert first != second


def test_chunk_id_changes_when_chunker_version_changes() -> None:
    """中文：该测试用于验证“文本块标识符`changes`当切块器版本`changes`”相关行为。

    English: Ensure a new chunking algorithm cannot collide with an old chunk identity.
    """

    # 中文：变量 `checksum` 用于保存“校验和”相关数据；其精确定义与约束见下方英文说明。
    # English: Content checksum represents the normalized chunk body.
    checksum = content_sha256("Evidence text")
    # 中文：变量 `first` 用于保存“第一项”相关数据；其精确定义与约束见下方英文说明。
    # English: Version-one identity.
    first = stable_chunk_id("tenant-a", "ver_abc", 0, checksum, "chunker-v1")
    # 中文：变量 `second` 用于保存“第二项”相关数据；其精确定义与约束见下方英文说明。
    # English: Version-two identity.
    second = stable_chunk_id("tenant-a", "ver_abc", 0, checksum, "chunker-v2")

    assert first != second


def test_negative_chunk_ordinal_is_rejected() -> None:
    """中文：该测试用于验证“负数文本块序号为被拒绝的”相关行为。

    English: Ensure invalid deterministic chunk positions fail before persistence.
    """

    with pytest.raises(ValidationError):
        stable_chunk_id("tenant-a", "ver_abc", -1, content_sha256("x"), "chunker-v1")
