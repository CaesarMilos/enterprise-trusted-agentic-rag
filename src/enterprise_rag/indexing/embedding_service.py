"""中文：本模块负责实现“向量嵌入服务”相关功能。

English: Batch provider embeddings, validate dimensions, and apply L2 normalization.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

from enterprise_rag.core.enums import ErrorCategory
from enterprise_rag.core.exceptions import ModelProviderError, error_detail
from enterprise_rag.domain.protocols.models import EmbeddingProvider
from enterprise_rag.indexing.provider_invocation import embed_with_timeout


class EmbeddingService:
    """中文：该类用于表示或实现“向量嵌入服务（EmbeddingService）”的职责。

    English: Create finite normalized vectors while preserving input order.
    """

    def __init__(
        self,
        provider: EmbeddingProvider,
        batch_size: int,
        expected_dimension: int = 0,
    ) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store the provider and validated batching constraints.
        """

        if batch_size < 1 or expected_dimension < 0:
            raise ValueError("batch_size must be positive and expected_dimension non-negative")
        # 中文：变量 `_provider` 用于保存“提供方”相关数据；其精确定义与约束见下方英文说明。
        # English: Provider implements either local or remote embedding behavior.
        self._provider = provider
        # 中文：变量 `_batch_size` 用于保存“批量`size`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Batch size bounds provider memory and request payloads.
        self._batch_size = batch_size
        # 中文：变量 `_expected_dimension` 用于保存“`expected``dimension`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Zero accepts the first provider-reported dimension.
        self._expected_dimension = expected_dimension

    @property
    def fingerprint(self) -> str:
        """中文：该函数或方法负责“指纹”相关处理。

        English: Expose the configured provider fingerprint for index manifests.
        """

        return self._provider.fingerprint

    def embed(
        self,
        texts: Sequence[str],
        *,
        timeout_seconds: float | None = None,
    ) -> NDArray[np.float32]:
        """中文：该函数或方法负责“向量化”相关处理。

        English: Return a two-dimensional float32 matrix of normalized embeddings.
        """

        if not texts:
            # 中文：未知真实维度的空计划使用一维占位矩阵，不会生成或搜索任何向量行。
            # English: Empty build plans use a one-dimensional placeholder when the provider
            # dimension is unknown; no row is embedded or searched.
            placeholder_dimension = self._expected_dimension or 1
            return np.empty((0, placeholder_dimension), dtype=np.float32)
        # 中文：变量 `vectors` 用于保存“`vectors`”相关数据；其精确定义与约束见下方英文说明。
        # English: Provider outputs are accumulated in stable batch order.
        vectors: list[Sequence[float]] = []
        for start in range(0, len(texts), self._batch_size):
            # 中文：变量 `batch` 用于保存“批量”相关数据；其精确定义与约束见下方英文说明。
            # English: Current batch retains exact caller ordering.
            batch = texts[start : start + self._batch_size]
            try:
                batch_vectors = embed_with_timeout(self._provider, batch, timeout_seconds)
            except Exception as exc:
                raise ModelProviderError(
                    error_detail(
                        "EMBEDDING_PROVIDER_FAILED",
                        ErrorCategory.MODEL,
                        "The embedding provider failed while building vectors.",
                    )
                ) from exc
            if len(batch_vectors) != len(batch):
                raise ModelProviderError(
                    error_detail(
                        "EMBEDDING_COUNT_MISMATCH",
                        ErrorCategory.MODEL,
                        "The embedding provider returned an unexpected vector count.",
                    )
                )
            vectors.extend(batch_vectors)
        # 中文：本步骤涉及向量，具体约束见下方英文说明。
        # English: Numeric conversion also rejects ragged vector lengths.
        try:
            matrix = np.asarray(vectors, dtype=np.float32)
        except ValueError as exc:
            raise ModelProviderError(
                error_detail(
                    "EMBEDDING_DIMENSION_MISMATCH",
                    ErrorCategory.MODEL,
                    "The embedding provider returned inconsistent vector dimensions.",
                )
            ) from exc
        if matrix.ndim != 2 or matrix.shape[1] == 0:
            raise ModelProviderError(
                error_detail(
                    "INVALID_EMBEDDING_SHAPE",
                    ErrorCategory.MODEL,
                    "The embedding provider returned an invalid matrix shape.",
                )
            )
        if self._expected_dimension and matrix.shape[1] != self._expected_dimension:
            raise ModelProviderError(
                error_detail(
                    "UNEXPECTED_EMBEDDING_DIMENSION",
                    ErrorCategory.MODEL,
                    "The embedding dimension does not match configuration.",
                    expected=str(self._expected_dimension),
                    actual=str(matrix.shape[1]),
                )
            )
        if not np.isfinite(matrix).all():
            raise ModelProviderError(
                error_detail(
                    "NON_FINITE_EMBEDDING",
                    ErrorCategory.MODEL,
                    "The embedding provider returned NaN or infinite values.",
                )
            )
        # 中文：变量 `norms` 用于保存“`norms`”相关数据；其精确定义与约束见下方英文说明。
        # English: Norms convert inner product into cosine similarity.
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        if np.any(norms == 0):
            raise ModelProviderError(
                error_detail(
                    "ZERO_NORM_EMBEDDING",
                    ErrorCategory.MODEL,
                    "The embedding provider returned an all-zero vector.",
                )
            )
        return np.asarray(matrix / norms, dtype=np.float32)

    def embed_query(
        self,
        query: str,
        *,
        timeout_seconds: float | None = None,
    ) -> NDArray[np.float32]:
        """中文：该函数或方法负责“向量化查询”相关处理。

        English: Return one normalized query vector.
        """

        return np.asarray(
            self.embed((query,), timeout_seconds=timeout_seconds)[0],
            dtype=np.float32,
        )
