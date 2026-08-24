"""中文：本模块负责实现“校验器”相关功能。

English: Validate upload size, extension, magic bytes, non-emptiness, and checksum.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from enterprise_rag.core.enums import ErrorCategory
from enterprise_rag.core.exceptions import ValidationError, error_detail
from enterprise_rag.core.ids import content_sha256

# 中文：变量 `_BINARY_SIGNATURES` 用于保存“`binary``signatures`”相关数据；
# 其精确定义与约束见下方英文说明。
# English: Known binary signatures used to prevent extension-only type spoofing.
_BINARY_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "pdf": (b"%PDF-",),
}


@dataclass(frozen=True, slots=True)
class ValidatedUpload:
    """中文：该类用于表示或实现“已校验的上传（ValidatedUpload）”的职责。

    English: Describe a validated local upload without retaining its bytes in memory.
    """

    # 中文：变量 `path` 用于保存“`path`”相关数据；其精确定义与约束见下方英文说明。
    # English: Canonical local path supplied to storage or a loader.
    path: Path
    # 中文：变量 `filename` 用于保存“`filename`”相关数据；其精确定义与约束见下方英文说明。
    # English: Safe leaf filename used only for display and extension selection.
    filename: str
    # 中文：变量 `media_type` 用于保存“`media``type`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Verified lowercase document type.
    media_type: str
    # 中文：变量 `content_hash` 用于保存“`content``hash`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: SHA-256 checksum of the original bytes.
    content_hash: str
    # 中文：变量 `size_bytes` 用于保存“`size``bytes`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Original byte length.
    size_bytes: int


class UploadValidator:
    """中文：该类用于表示或实现“上传校验器（UploadValidator）”的职责。

    English: Validate local upload files before they enter durable storage or parsing.
    """

    def __init__(self, allowed_extensions: tuple[str, ...], max_file_size_mb: int) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store normalized allowed types and the byte-size ceiling.
        """

        # 中文：变量 `_allowed_extensions` 用于保存“`allowed``extensions`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Allowed types are normalized once to avoid inconsistent comparisons.
        self._allowed_extensions = frozenset(
            extension.lower().lstrip(".") for extension in allowed_extensions
        )
        # 中文：变量 `_max_size_bytes` 用于保存“`max``size``bytes`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Byte ceiling uses mebibytes, matching storage and infrastructure
        #   conventions.
        self._max_size_bytes = max_file_size_mb * 1024 * 1024

    def validate(self, path: Path, filename: str) -> ValidatedUpload:
        """中文：该函数或方法负责“校验”相关处理。

        English: Validate the exact local file and return stable metadata.
        """

        # 中文：变量 `resolved_path` 用于保存“`resolved``path`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Canonical path must identify one ordinary file.
        resolved_path = path.expanduser().resolve()
        if not resolved_path.is_file():
            raise ValidationError(
                error_detail(
                    "UPLOAD_NOT_FOUND",
                    ErrorCategory.VALIDATION,
                    "The uploaded temporary file does not exist.",
                )
            )
        # 中文：变量 `safe_filename` 用于保存“安全`filename`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: User-provided directories are discarded from the display filename.
        safe_filename = Path(filename.replace("\\", "/")).name
        # 中文：变量 `extension` 用于保存“`extension`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Extension is only one input to type verification.
        extension = Path(safe_filename).suffix.lower().lstrip(".")
        if extension not in self._allowed_extensions:
            raise ValidationError(
                error_detail(
                    "UNSUPPORTED_DOCUMENT_TYPE",
                    ErrorCategory.VALIDATION,
                    "The uploaded file extension is not supported.",
                    extension=extension or "(none)",
                )
            )
        # 中文：变量 `size_bytes` 用于保存“`size``bytes`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: File size is read from metadata before loading bytes.
        size_bytes = resolved_path.stat().st_size
        if size_bytes <= 0:
            raise ValidationError(
                error_detail(
                    "EMPTY_UPLOAD",
                    ErrorCategory.VALIDATION,
                    "The uploaded file is empty.",
                )
            )
        if size_bytes > self._max_size_bytes:
            raise ValidationError(
                error_detail(
                    "UPLOAD_TOO_LARGE",
                    ErrorCategory.VALIDATION,
                    "The uploaded file exceeds the configured size limit.",
                )
            )
        # 中文：本注释说明当前代码步骤的用途、约束或设计原因。
        # English: Header is sufficient for known binary container signatures.
        with resolved_path.open("rb") as source:
            header = source.read(16)
        expected_signatures = _BINARY_SIGNATURES.get(extension)
        if expected_signatures and not header.startswith(expected_signatures):
            raise ValidationError(
                error_detail(
                    "DOCUMENT_SIGNATURE_MISMATCH",
                    ErrorCategory.VALIDATION,
                    "The file content does not match its extension.",
                    extension=extension,
                )
            )
        # 中文：变量 `checksum` 用于保存“校验和”相关数据；其精确定义与约束见下方英文说明。
        # English: Full checksum is calculated once after inexpensive rejection checks.
        checksum = content_sha256(resolved_path.read_bytes())
        return ValidatedUpload(
            path=resolved_path,
            filename=safe_filename,
            media_type=extension,
            content_hash=checksum,
            size_bytes=size_bytes,
        )
