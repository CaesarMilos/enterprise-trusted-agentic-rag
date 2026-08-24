"""中文：本模块负责实现“加载器`registry`”相关功能。

English: Register document loaders and select one only after type validation.
"""

from __future__ import annotations

from enterprise_rag.core.enums import ErrorCategory
from enterprise_rag.core.exceptions import ValidationError, error_detail
from enterprise_rag.ingestion.loaders.base import DocumentLoader


class LoaderRegistry:
    """中文：该类用于表示或实现“加载器`registry`（LoaderRegistry）”的职责。

    English: Map verified lowercase document types to unique loader instances.
    """

    def __init__(self, loaders: tuple[DocumentLoader, ...]) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Build the registry and reject ambiguous duplicate type handlers.
        """

        # 中文：变量 `_loaders` 用于保存“`loaders`”相关数据；其精确定义与约束见下方英文说明。
        # English: Type-to-loader mapping is immutable by convention after construction.
        self._loaders: dict[str, DocumentLoader] = {}
        for loader in loaders:
            for media_type in loader.media_types:
                if media_type in self._loaders:
                    raise ValueError(f"duplicate loader for media type: {media_type}")
                self._loaders[media_type] = loader

    def get(self, media_type: str) -> DocumentLoader:
        """中文：该函数或方法负责“读取目标对象”相关处理。

        English: Return the loader for a previously verified document type.
        """

        # 中文：变量 `normalized_type` 用于保存“`normalized``type`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Registry keys are normalized to lowercase without a leading dot.
        normalized_type = media_type.lower().lstrip(".")
        try:
            return self._loaders[normalized_type]
        except KeyError as exc:
            raise ValidationError(
                error_detail(
                    "UNSUPPORTED_DOCUMENT_TYPE",
                    ErrorCategory.VALIDATION,
                    "No loader is registered for the verified document type.",
                    media_type=normalized_type,
                )
            ) from exc
