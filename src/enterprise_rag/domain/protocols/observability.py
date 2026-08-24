"""中文：本模块负责实现“可观测性”相关功能。

English: Define non-blocking trace, metric, and model-cost recording ports.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from enterprise_rag.domain.models import TraceRecord


class TraceRecorder(Protocol):
    """中文：该类用于表示或实现“追踪记录器（TraceRecorder）”的职责。

    English: Record redacted workflow summaries and append-only steps.
    """

    def start(self, trace: TraceRecord) -> None:
        """中文：该函数或方法负责“开始”相关处理。

        English: Create a trace without storing raw prompts or document text.
        """

    def append_step(
        self,
        trace_id: str,
        name: str,
        attributes: Mapping[str, Any],
    ) -> None:
        """中文：该函数或方法负责“追加步骤”相关处理。

        English: Append one safe workflow decision or measurement.
        """

    def finish(self, trace_id: str, status: str, attributes: Mapping[str, Any]) -> None:
        """中文：该函数或方法负责“结束”相关处理。

        English: Finalize a trace with a terminal status and safe aggregate attributes.
        """


class MetricRecorder(Protocol):
    """中文：该类用于表示或实现“指标记录器（MetricRecorder）”的职责。

    English: Record operational counters and latency distributions.
    """

    def increment(self, name: str, value: int = 1, **labels: str) -> None:
        """中文：该函数或方法负责“递增”相关处理。

        English: Increase a named counter by a positive integer.
        """

    def observe(self, name: str, value: float, **labels: str) -> None:
        """中文：该函数或方法负责“观测”相关处理。

        English: Add a numeric observation such as duration or token count.
        """


class CostTracker(Protocol):
    """中文：该类用于表示或实现“成本跟踪器（CostTracker）”的职责。

    English: Track provider usage without assuming a price is known.
    """

    def record(
        self,
        trace_id: str,
        provider_fingerprint: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """中文：该函数或方法负责“记录”相关处理。

        English: Record one provider call's token usage and computable cost.
        """
