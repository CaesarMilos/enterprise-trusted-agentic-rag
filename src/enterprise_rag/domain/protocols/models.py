"""中文：本模块负责实现“模型”相关功能。

English: Define interchangeable language, embedding, and reranking provider ports.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ModelUsage:
    """中文：该类用于表示或实现“模型用量（ModelUsage）”的职责。

    English: Describe token usage reported by a model provider.
    """

    # 中文：变量 `input_tokens` 用于保存“输入词元”相关数据；其精确定义与约束见下方英文说明。
    # English: Input or prompt tokens consumed.
    input_tokens: int
    # 中文：变量 `output_tokens` 用于保存“输出词元”相关数据；其精确定义与约束见下方英文说明。
    # English: Output or completion tokens produced.
    output_tokens: int


@dataclass(frozen=True, slots=True)
class ModelResponse:
    """中文：该类用于表示或实现“模型响应（ModelResponse）”的职责。

    English: Represent provider-neutral generated text and usage.
    """

    # 中文：变量 `text` 用于保存“文本”相关数据；其精确定义与约束见下方英文说明。
    # English: Generated model text.
    text: str
    # 中文：变量 `usage` 用于保存“`usage`”相关数据；其精确定义与约束见下方英文说明。
    # English: Provider-reported usage.
    usage: ModelUsage
    # 中文：变量 `model` 用于保存“模型”相关数据；其精确定义与约束见下方英文说明。
    # English: Provider model identifier used for the call.
    model: str


class EmbeddingProvider(Protocol):
    """中文：该类用于表示或实现“向量嵌入提供方（EmbeddingProvider）”的职责。

    English: Create normalized-compatible numeric vectors for documents and queries.
    """

    @property
    def fingerprint(self) -> str:
        """中文：该函数或方法负责“指纹”相关处理。

        English: Return a stable provider, model, and dimension fingerprint.
        """

    def embed(
        self,
        texts: Sequence[str],
        *,
        timeout_seconds: float | None = None,
    ) -> Sequence[Sequence[float]]:
        """中文：该函数或方法负责“向量化”相关处理。

        English: Embed an ordered text batch and preserve input order.
        """


class LLMProvider(Protocol):
    """中文：该类用于表示或实现“大语言模型提供方（LLMProvider）”的职责。

    English: Generate text through a provider-neutral chat interface.
    """

    @property
    def fingerprint(self) -> str:
        """中文：该函数或方法负责“指纹”相关处理。

        English: Return a stable provider and model fingerprint.
        """

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        metadata: Mapping[str, str] | None = None,
        *,
        timeout_seconds: float | None = None,
    ) -> ModelResponse:
        """中文：该函数或方法负责“完成一次模型调用”相关处理。

        English: Generate one response capped by an optional remaining global deadline.
        """


class RerankerProvider(Protocol):
    """中文：该类用于表示或实现“重排器提供方（RerankerProvider）”的职责。

    English: Score query-passage pairs in an order-independent numeric space.
    """

    @property
    def fingerprint(self) -> str:
        """中文：该函数或方法负责“指纹”相关处理。

        English: Return a stable provider and model fingerprint.
        """

    def score(
        self,
        query: str,
        passages: Sequence[str],
        *,
        timeout_seconds: float | None = None,
    ) -> Sequence[float]:
        """中文：该函数或方法负责“计算相关性分数”相关处理。

        English: Return one relevance score for each passage in input order.
        """
