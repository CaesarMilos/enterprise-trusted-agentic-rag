"""中文：本模块负责实现“标识符”相关功能。

English: Generate random entity IDs and deterministic content-derived IDs.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Iterable

from enterprise_rag.core.enums import ErrorCategory
from enterprise_rag.core.exceptions import ValidationError, error_detail

# 中文：变量 `_ID_NAMESPACE` 用于保存“标识符`namespace`”相关数据；
# 其精确定义与约束见下方英文说明。
# English: Namespace isolates deterministic IDs created by this application.
_ID_NAMESPACE = uuid.UUID("9681e3db-df3d-4bcf-91b7-aec88ad05587")
# 中文：变量 `_PUBLIC_ID_PATTERN` 用于保存“`public`标识符`pattern`”相关数据；
# 其精确定义与约束见下方英文说明。
# English: Public IDs use a readable prefix followed by 32 hexadecimal characters.
_PUBLIC_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,23}_[0-9a-f]{32}$")


def new_id(prefix: str) -> str:
    """中文：该函数或方法负责“新建标识符”相关处理。

    English: Return a random, readable public identifier with the supplied prefix.
    """

    _validate_prefix(prefix)
    # 中文：变量 `payload` 用于保存“载荷”相关数据；其精确定义与约束见下方英文说明。
    # English: Random UUID payload prevents predictable identifiers at trust boundaries.
    payload = uuid.uuid4().hex
    return f"{prefix}_{payload}"


def stable_id(prefix: str, parts: Iterable[str]) -> str:
    """中文：该函数或方法负责“稳定标识符”相关处理。

    English: Return a deterministic identifier for an ordered collection of parts.
    """

    _validate_prefix(prefix)
    # 中文：变量 `canonical` 用于保存“`canonical`”相关数据；其精确定义与约束见下方英文说明。
    # English: Length prefixes prevent ambiguous concatenations such as ("ab", "c") and
    #   ("a", "bc").
    canonical = "|".join(f"{len(part)}:{part}" for part in parts)
    # 中文：变量 `payload` 用于保存“载荷”相关数据；其精确定义与约束见下方英文说明。
    # English: UUID5 provides a stable 128-bit value within the application namespace.
    payload = uuid.uuid5(_ID_NAMESPACE, canonical).hex
    return f"{prefix}_{payload}"


def stable_chunk_id(
    tenant_id: str,
    document_version_id: str,
    ordinal: int,
    content_hash: str,
    chunker_version: str,
) -> str:
    """中文：该函数或方法负责“稳定文本块标识符”相关处理。

    English: Generate the same chunk ID for the same version, content, order, and chunker.
    """

    if ordinal < 0:
        raise ValidationError(
            error_detail(
                "INVALID_CHUNK_ORDINAL",
                ErrorCategory.VALIDATION,
                "Chunk ordinal must be non-negative.",
            )
        )
    # 中文：变量 `identity_parts` 用于保存“`identity``parts`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Ordered identity components fully define one deterministic chunk.
    identity_parts = (
        tenant_id,
        document_version_id,
        str(ordinal),
        content_hash,
        chunker_version,
    )
    return stable_id("chk", identity_parts)


def content_sha256(content: bytes | str) -> str:
    """中文：该函数或方法负责“内容SHA-256”相关处理。

    English: Return a lowercase SHA-256 checksum for bytes or UTF-8 text.
    """

    # 中文：变量 `payload` 用于保存“载荷”相关数据；其精确定义与约束见下方英文说明。
    # English: Byte representation is the canonical checksum input.
    payload = content.encode("utf-8") if isinstance(content, str) else content
    return hashlib.sha256(payload).hexdigest()


def validate_public_id(value: str, expected_prefix: str | None = None) -> str:
    """中文：该函数或方法负责“校验公开标识符”相关处理。

    English: Validate a public identifier and return it unchanged.
    """

    if not _PUBLIC_ID_PATTERN.fullmatch(value):
        raise ValidationError(
            error_detail(
                "INVALID_PUBLIC_ID",
                ErrorCategory.VALIDATION,
                "The supplied identifier has an invalid format.",
            )
        )
    if expected_prefix is not None and not value.startswith(f"{expected_prefix}_"):
        raise ValidationError(
            error_detail(
                "UNEXPECTED_ID_TYPE",
                ErrorCategory.VALIDATION,
                "The supplied identifier is not the expected entity type.",
                expected_prefix=expected_prefix,
            )
        )
    return value


def _validate_prefix(prefix: str) -> None:
    """中文：该内部函数负责“校验前缀”相关处理。

    English: Reject prefixes that would make public IDs ambiguous or unsafe.
    """

    if not re.fullmatch(r"[a-z][a-z0-9_]{1,23}", prefix):
        raise ValidationError(
            error_detail(
                "INVALID_ID_PREFIX",
                ErrorCategory.VALIDATION,
                "ID prefixes must contain 2-24 lowercase letters, digits, or underscores.",
            )
        )
