"""中文：提供覆盖整个 Agent 工作流的单调时钟硬截止时间预算。

English: Provide a monotonic hard-deadline budget spanning the complete agent workflow.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from time import monotonic

from enterprise_rag.core.enums import ErrorCategory
from enterprise_rag.core.exceptions import OperationTimeoutError, error_detail


@dataclass(frozen=True, slots=True)
class DeadlineBudget:
    """中文：冻结全局截止点，并为所有子调用计算不超过剩余预算的超时。

    English: Freeze a global deadline and cap every child-call timeout by remaining time.
    """

    # 中文：绝对单调时钟截止点，不受系统时间回拨影响。
    # English: Absolute monotonic deadline, immune to wall-clock adjustments.
    deadline: float
    # 中文：可注入时钟使超时边界测试完全确定。
    # English: Injectable clock makes deadline edge tests deterministic.
    clock: Callable[[], float] = field(default=monotonic, repr=False, compare=False)

    @classmethod
    def from_timeout(
        cls,
        timeout_seconds: float,
        *,
        clock: Callable[[], float] = monotonic,
    ) -> DeadlineBudget:
        """中文：根据当前单调时间和正数总预算创建截止时间。

        English: Create a deadline from the current monotonic time and a positive total budget.
        """

        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        return cls(deadline=clock() + timeout_seconds, clock=clock)

    def remaining_seconds(self) -> float:
        """中文：返回非负剩余秒数；超时后固定为零。

        English: Return non-negative remaining seconds, clamped to zero after expiry.
        """

        return max(0.0, self.deadline - self.clock())

    def child_timeout(self, configured_seconds: float, *, minimum_seconds: float = 0.05) -> float:
        """中文：计算子调用上限；预算不足时在发起外部调用前直接失败。

        English: Cap a child call and fail before I/O when too little global budget remains.
        """

        self.checkpoint("before_child_call")
        remaining = self.remaining_seconds()
        timeout = min(configured_seconds, remaining)
        if timeout < minimum_seconds:
            self._raise_timeout("insufficient_child_budget")
        return timeout

    def child_budget(self, configured_seconds: float, *, stage: str) -> DeadlineBudget:
        """中文：创建不超过全局剩余时间的单调子预算。

        English: Create a monotonic child budget capped by the global remaining time.
        """

        timeout = self.timeout_for_call(stage, configured_seconds=configured_seconds)
        return DeadlineBudget.from_timeout(timeout, clock=self.clock)

    def timeout_for_call(
        self,
        stage: str,
        *,
        configured_seconds: float | None = None,
        minimum_seconds: float = 0.001,
    ) -> float:
        """中文：返回底层调用可使用的剩余超时，预算不足时拒绝发起调用。

        English: Return timeout available to a lower-level call or reject it before dispatch.
        """

        self.checkpoint(stage)
        remaining = self.remaining_seconds()
        timeout = remaining if configured_seconds is None else min(remaining, configured_seconds)
        if timeout < minimum_seconds:
            self._raise_timeout(stage)
        return timeout

    def checkpoint(self, stage: str) -> None:
        """中文：在节点前后执行硬检查，确保迟到结果永远不会作为正常答案返回。

        English: Enforce the hard deadline before and after nodes so late results are discarded.
        """

        if self.remaining_seconds() <= 0:
            self._raise_timeout(stage)

    def _raise_timeout(self, stage: str) -> None:
        """中文：将超时统一转换为稳定、可追踪的领域异常。

        English: Convert expiry into one stable and traceable domain exception.
        """

        raise OperationTimeoutError(
            error_detail(
                "AGENT_DEADLINE_EXCEEDED",
                ErrorCategory.TIMEOUT,
                "The agent workflow exceeded its hard deadline.",
                stage=stage,
            )
        )
