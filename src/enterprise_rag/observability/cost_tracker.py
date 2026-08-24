"""中文：本模块负责实现“成本跟踪器”相关功能。

English: Track model token usage and compute cost only when an explicit price is configured.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True, slots=True)
class UsageRecord:
    """中文：该类用于表示或实现“用量记录（UsageRecord）”的职责。

    English: Represent one provider call's usage and optional computed cost.
    """

    # 中文：变量 `trace_id` 用于保存“追踪标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable trace identifier.
    trace_id: str
    # 中文：变量 `provider_fingerprint` 用于保存“提供方指纹”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Provider and model fingerprint.
    provider_fingerprint: str
    # 中文：变量 `input_tokens` 用于保存“输入词元”相关数据；其精确定义与约束见下方英文说明。
    # English: Input token count.
    input_tokens: int
    # 中文：变量 `output_tokens` 用于保存“输出词元”相关数据；其精确定义与约束见下方英文说明。
    # English: Output token count.
    output_tokens: int
    # 中文：变量 `cost` 用于保存“成本”相关数据；其精确定义与约束见下方英文说明。
    # English: Computed currency cost, or None when pricing is unknown.
    cost: float | None


class ModelCostTracker:
    """中文：该类用于表示或实现“模型成本跟踪器（ModelCostTracker）”的职责。

    English: Record token usage without inventing unknown provider prices.
    """

    def __init__(
        self,
        prices_per_million: dict[str, tuple[float, float]] | None = None,
    ) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store explicit input/output prices indexed by provider fingerprint.
        """

        # 中文：变量 `_prices` 用于保存“`prices`”相关数据；其精确定义与约束见下方英文说明。
        # English: Price tuple contains input and output currency cost per million tokens.
        self._prices = prices_per_million or {}
        # 中文：变量 `_records` 用于保存“`records`”相关数据；其精确定义与约束见下方英文说明。
        # English: Ordered records support trace-level inspection.
        self._records: list[UsageRecord] = []
        # 中文：变量 `_lock` 用于保存“`lock`”相关数据；其精确定义与约束见下方英文说明。
        # English: Lock protects concurrent provider-call recording.
        self._lock = Lock()

    def record(
        self,
        trace_id: str,
        provider_fingerprint: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """中文：该函数或方法负责“记录”相关处理。

        English: Record usage and compute cost only from an exact configured fingerprint.
        """

        # 中文：变量 `safe_input` 用于保存“安全输入”相关数据；其精确定义与约束见下方英文说明。
        # English: Negative provider values are normalized defensively.
        safe_input = max(0, input_tokens)
        safe_output = max(0, output_tokens)
        # 中文：变量 `price` 用于保存“`price`”相关数据；其精确定义与约束见下方英文说明。
        # English: Unknown price remains semantically unknown instead of falsely reporting
        #   zero.
        price = self._prices.get(provider_fingerprint)
        cost = (
            (safe_input * price[0] + safe_output * price[1]) / 1_000_000
            if price is not None
            else None
        )
        with self._lock:
            self._records.append(
                UsageRecord(
                    trace_id=trace_id,
                    provider_fingerprint=provider_fingerprint,
                    input_tokens=safe_input,
                    output_tokens=safe_output,
                    cost=cost,
                )
            )

    def records(self) -> tuple[UsageRecord, ...]:
        """中文：该函数或方法负责“记录”相关处理。

        English: Return an immutable snapshot of recorded usage.
        """

        with self._lock:
            return tuple(self._records)
