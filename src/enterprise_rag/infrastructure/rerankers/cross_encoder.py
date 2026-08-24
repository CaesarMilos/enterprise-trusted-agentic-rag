"""中文：本模块负责实现“交叉编码器”相关功能。

English: Score query-passage pairs with a lazily loaded sentence-transformers CrossEncoder.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


class CrossEncoderReranker:
    """中文：该类用于表示或实现“交叉编码器重排器（CrossEncoderReranker）”的职责。

    English: Implement the reranker port with a local cross-encoder model.
    """

    def __init__(self, model_name: str, device: str | None = None) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store model configuration without loading weights during process startup.
        """

        # 中文：变量 `_model_name` 用于保存“模型`name`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Model identifier is retained in evaluation fingerprints.
        self._model_name = model_name
        # 中文：变量 `_device` 用于保存“`device`”相关数据；其精确定义与约束见下方英文说明。
        # English: Optional explicit inference device.
        self._device = device
        # 中文：变量 `_model` 用于保存“模型”相关数据；其精确定义与约束见下方英文说明。
        # English: Model remains unloaded until the first reranking request.
        self._model: Any | None = None

    @property
    def fingerprint(self) -> str:
        """中文：该函数或方法负责“指纹”相关处理。

        English: Return a stable provider and model fingerprint.
        """

        return f"cross-encoder:{self._model_name}"

    def score(self, query: str, passages: Sequence[str]) -> Sequence[float]:
        """中文：该函数或方法负责“计算相关性分数”相关处理。

        English: Return one float score per query-passage pair.
        """

        # 中文：变量 `pairs` 用于保存“`pairs`”相关数据；其精确定义与约束见下方英文说明。
        # English: Pair ordering mirrors passage input ordering.
        pairs = [(query, passage) for passage in passages]
        scores = self._get_model().predict(pairs, show_progress_bar=False)
        return tuple(float(score) for score in scores)

    def _get_model(self) -> Any:
        """中文：该内部函数负责“获取模型”相关处理。

        English: Load and cache the configured cross-encoder exactly once.
        """

        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
            except ImportError as exc:
                raise RuntimeError(
                    "sentence-transformers is required; install the local-models extra"
                ) from exc
            self._model = CrossEncoder(self._model_name, device=self._device)
        return self._model
