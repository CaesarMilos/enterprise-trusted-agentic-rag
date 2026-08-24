"""中文：本模块负责实现“追踪模型”相关功能。

English: Define redacted append-only trace events and model-call summaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class TraceStep:
    """中文：该类用于表示或实现“追踪步骤（TraceStep）”的职责。

    English: Represent one safe append-only workflow decision or measurement.
    """

    # 中文：变量 `trace_id` 用于保存“追踪标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable trace identifier.
    trace_id: str
    # 中文：变量 `sequence` 用于保存“`sequence`”相关数据；其精确定义与约束见下方英文说明。
    # English: Monotonic zero-based step position assigned by the recorder.
    sequence: int
    # 中文：变量 `name` 用于保存“`name`”相关数据；其精确定义与约束见下方英文说明。
    # English: Short component or decision name.
    name: str
    # 中文：变量 `attributes` 用于保存“`attributes`”相关数据；其精确定义与约束见下方英文说明。
    # English: Safe structured values excluding raw prompts and chunk text.
    attributes: dict[str, Any] = field(default_factory=dict)
    # 中文：变量 `created_at` 用于保存“`created``at`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: UTC event timestamp.
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class ModelCallTrace:
    """中文：该类用于表示或实现“模型调用追踪（ModelCallTrace）”的职责。

    English: Represent safe usage and latency data for one provider call.
    """

    # 中文：变量 `trace_id` 用于保存“追踪标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable trace identifier.
    trace_id: str
    # 中文：变量 `provider_fingerprint` 用于保存“提供方指纹”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Provider and model fingerprint.
    provider_fingerprint: str
    # 中文：变量 `operation` 用于保存“`operation`”相关数据；其精确定义与约束见下方英文说明。
    # English: Operation label such as query_rewrite or answer_generation.
    operation: str
    # 中文：变量 `input_tokens` 用于保存“输入词元”相关数据；其精确定义与约束见下方英文说明。
    # English: Provider-reported input token count.
    input_tokens: int
    # 中文：变量 `output_tokens` 用于保存“输出词元”相关数据；其精确定义与约束见下方英文说明。
    # English: Provider-reported output token count.
    output_tokens: int
    # 中文：变量 `duration_ms` 用于保存“`duration``ms`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Observed call duration in milliseconds.
    duration_ms: float
    # 中文：变量 `succeeded` 用于保存“成功的”相关数据；其精确定义与约束见下方英文说明。
    # English: Whether the call completed successfully.
    succeeded: bool


@dataclass(frozen=True, slots=True)
class ErrorEvent:
    """中文：该类用于表示或实现“错误事件（ErrorEvent）”的职责。

    English: Represent one redacted typed workflow failure.
    """

    # 中文：变量 `trace_id` 用于保存“追踪标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable trace identifier.
    trace_id: str
    # 中文：变量 `error_code` 用于保存“错误`code`”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable application error code.
    error_code: str
    # 中文：变量 `category` 用于保存“`category`”相关数据；其精确定义与约束见下方英文说明。
    # English: Safe error category.
    category: str
    # 中文：变量 `component` 用于保存“`component`”相关数据；其精确定义与约束见下方英文说明。
    # English: Component in which the failure occurred.
    component: str
    # 中文：变量 `degraded` 用于保存“`degraded`”相关数据；其精确定义与约束见下方英文说明。
    # English: Whether a fallback allowed execution to continue.
    degraded: bool = False
