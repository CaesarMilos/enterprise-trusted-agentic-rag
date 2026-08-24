"""中文：本模块负责实现“文件存储”相关功能。

English: Provide reusable validation helpers for concrete file-store adapters.
"""

from __future__ import annotations

import re
from pathlib import Path

from enterprise_rag.core.enums import ErrorCategory
from enterprise_rag.core.exceptions import StorageError, error_detail

# 中文：变量 `_SAFE_SEGMENT_PATTERN` 用于保存“安全`segment``pattern`”相关数据；
# 其精确定义与约束见下方英文说明。
# English: Opaque path segments are deliberately narrower than public user-supplied names.
_SAFE_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def safe_segment(value: str, field_name: str) -> str:
    """中文：该函数或方法负责“安全路径段”相关处理。

    English: Validate one adapter-controlled filesystem segment and return it unchanged.
    """

    if not _SAFE_SEGMENT_PATTERN.fullmatch(value) or value in {".", ".."}:
        raise StorageError(
            error_detail(
                "UNSAFE_STORAGE_SEGMENT",
                ErrorCategory.STORAGE,
                "A storage identifier contains unsafe path characters.",
                field=field_name,
            )
        )
    return value


def sanitized_extension(filename: str) -> str:
    """中文：该函数或方法负责“已净化的`extension`”相关处理。

    English: Return a lowercase safe extension without trusting the rest of the filename.
    """

    # 中文：变量 `leaf_name` 用于保存“`leaf``name`”相关数据；其精确定义与约束见下方英文说明。
    # English: Path.name drops any user-supplied parent directories on every platform-like
    #   input.
    leaf_name = Path(filename.replace("\\", "/")).name
    # 中文：变量 `suffix` 用于保存“`suffix`”相关数据；其精确定义与约束见下方英文说明。
    # English: Suffix is retained only when it contains a short alphanumeric type label.
    suffix = Path(leaf_name).suffix.lower().lstrip(".")
    if not suffix or not re.fullmatch(r"[a-z0-9]{1,10}", suffix):
        return "bin"
    return suffix


def ensure_within_root(candidate: Path, root: Path) -> Path:
    """中文：该函数或方法负责“确保范围内`root`”相关处理。

    English: Resolve a candidate and reject any path escaping the configured root.
    """

    # 中文：变量 `resolved_candidate` 用于保存“`resolved`候选项”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Strict=False permits validation before the destination file exists.
    resolved_candidate = candidate.resolve(strict=False)
    resolved_root = root.resolve(strict=False)
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise StorageError(
            error_detail(
                "STORAGE_PATH_ESCAPE",
                ErrorCategory.STORAGE,
                "A resolved storage path escaped its configured root.",
            )
        ) from exc
    return resolved_candidate
