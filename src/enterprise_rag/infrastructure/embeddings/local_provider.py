"""中文：本模块负责实现“本地提供方”相关功能。

English: Create document and query embeddings with a lazily loaded sentence-transformers model.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast


class LocalEmbeddingProvider:
    """中文：该类用于表示或实现“本地向量嵌入提供方（LocalEmbeddingProvider）”的职责。

    English: Implement the embedding port with a local sentence-transformers model.
    """

    def __init__(self, model_name: str, device: str | None = None) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store model configuration without loading large weights during import.
        """

        # 中文：变量 `_model_name` 用于保存“模型`name`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Model name is retained in reproducibility fingerprints.
        self._model_name = model_name
        # 中文：变量 `_device` 用于保存“`device`”相关数据；其精确定义与约束见下方英文说明。
        # English: Optional explicit device supports CPU, CUDA, or MPS deployments.
        self._device = device
        # 中文：变量 `_model` 用于保存“模型”相关数据；其精确定义与约束见下方英文说明。
        # English: Model remains unloaded until the first embedding call.
        self._model: Any | None = None

    @property
    def fingerprint(self) -> str:
        """中文：该函数或方法负责“指纹”相关处理。

        English: Return a stable provider and model fingerprint.
        """

        return f"sentence-transformers:{self._model_name}"

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """中文：该函数或方法负责“向量化”相关处理。

        English: Return provider vectors in input order; normalization occurs in
        EmbeddingService.
        """

        # 中文：变量 `model` 用于保存“模型”相关数据；其精确定义与约束见下方英文说明。
        # English: Lazy loading keeps API health checks and non-embedding scripts
        #   lightweight.
        model = self._get_model()
        # 中文：变量 `vectors` 用于保存“`vectors`”相关数据；其精确定义与约束见下方英文说明。
        # English: Conversion to list keeps the domain protocol independent of NumPy.
        vectors = model.encode(
            list(texts),
            convert_to_numpy=True,
            normalize_embeddings=False,
            show_progress_bar=False,
        )
        return cast(list[list[float]], vectors.tolist())

    def _get_model(self) -> Any:
        """中文：该内部函数负责“获取模型”相关处理。

        English: Load and cache the configured model exactly once in this process.
        """

        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError(
                    "sentence-transformers is required; install the local-models extra"
                ) from exc
            # 中文：变量 `_model` 用于保存“模型”相关数据；其精确定义与约束见下方英文说明。
            # English: Device is omitted when auto-selection should be used.
            self._model = SentenceTransformer(self._model_name, device=self._device)
        return self._model
