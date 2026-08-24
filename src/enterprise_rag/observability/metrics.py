"""中文：本模块负责实现“指标”相关功能。

English: Aggregate process-local counters and numeric observations for health and demos.
"""

from __future__ import annotations

from collections import defaultdict
from threading import Lock


class InMemoryMetrics:
    """中文：该类用于表示或实现“在内存指标（InMemoryMetrics）”的职责。

    English: Provide a thread-safe lightweight metric recorder without external infrastructure.
    """

    def __init__(self) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Initialize empty counter and observation stores.
        """

        # 中文：变量 `_counters` 用于保存“`counters`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Counter key includes a sorted immutable label tuple.
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], int] = defaultdict(int)
        # 中文：变量 `_observations` 用于保存“`observations`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Observation key includes the same stable label representation.
        self._observations: dict[
            tuple[str, tuple[tuple[str, str], ...]],
            list[float],
        ] = defaultdict(list)
        # 中文：变量 `_lock` 用于保存“`lock`”相关数据；其精确定义与约束见下方英文说明。
        # English: Lock serializes process-local mutations and snapshots.
        self._lock = Lock()

    def increment(self, name: str, value: int = 1, **labels: str) -> None:
        """中文：该函数或方法负责“递增”相关处理。

        English: Increase a named counter by a non-negative integer.
        """

        if value < 0:
            raise ValueError("counter increments must be non-negative")
        # 中文：变量 `key` 用于保存“`key`”相关数据；其精确定义与约束见下方英文说明。
        # English: Sorted labels make equivalent keyword order share one series.
        key = (name, tuple(sorted(labels.items())))
        with self._lock:
            self._counters[key] += value

    def observe(self, name: str, value: float, **labels: str) -> None:
        """中文：该函数或方法负责“观测”相关处理。

        English: Append a numeric observation such as latency or token usage.
        """

        # 中文：变量 `key` 用于保存“`key`”相关数据；其精确定义与约束见下方英文说明。
        # English: Sorted labels make equivalent keyword order share one series.
        key = (name, tuple(sorted(labels.items())))
        with self._lock:
            self._observations[key].append(float(value))

    def snapshot(self) -> dict[str, object]:
        """中文：该函数或方法负责“快照”相关处理。

        English: Return a JSON-safe aggregate snapshot for administrators.
        """

        with self._lock:
            # 中文：变量 `counters` 用于保存“`counters`”相关数据；
            # 其精确定义与约束见下方英文说明。
            # English: Counter series are flattened into readable stable keys.
            counters = {
                _series_name(name, labels): value
                for (name, labels), value in self._counters.items()
            }
            # 中文：变量 `observations` 用于保存“`observations`”相关数据；
            # 其精确定义与约束见下方英文说明。
            # English: Observations expose count, mean, minimum, and maximum.
            observations = {
                _series_name(name, labels): {
                    "count": len(values),
                    "mean": sum(values) / len(values),
                    "min": min(values),
                    "max": max(values),
                }
                for (name, labels), values in self._observations.items()
                if values
            }
        return {"counters": counters, "observations": observations}


def _series_name(name: str, labels: tuple[tuple[str, str], ...]) -> str:
    """中文：该内部函数负责“序列名称”相关处理。

    English: Render one metric series key deterministically.
    """

    if not labels:
        return name
    label_text = ",".join(f"{key}={value}" for key, value in labels)
    return f"{name}{{{label_text}}}"
