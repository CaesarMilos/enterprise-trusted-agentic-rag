"""中文：为不可中断 Provider 提供有界线程执行、超时返回和容量保护。

English: Provide bounded thread execution, timeout return, and capacity protection for providers.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from threading import BoundedSemaphore, Lock
from typing import TypeVar

from enterprise_rag.core.deadline import DeadlineBudget
from enterprise_rag.core.enums import ErrorCategory
from enterprise_rag.core.exceptions import OperationTimeoutError, error_detail

ResultT = TypeVar("ResultT")


class BoundedExecutor:
    """中文：限制运行中和排队任务总数，防止超时 Provider 挤满线程池。

    English: Bound running and queued work so timed-out providers cannot exhaust the pool.
    """

    def __init__(self, max_workers: int, queue_capacity: int, thread_name_prefix: str) -> None:
        """中文：创建固定线程池和覆盖运行、排队任务的容量信号量。

        English: Create a fixed pool and capacity semaphore covering running and queued tasks.
        """

        if max_workers < 1 or queue_capacity < 0:
            raise ValueError("executor workers must be positive and queue capacity non-negative")
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=thread_name_prefix,
        )
        # 中文：容量等于线程数加允许排队数，提交时非阻塞获取。
        # English: Capacity covers workers plus queued tasks and is acquired without blocking.
        self._capacity = BoundedSemaphore(max_workers + queue_capacity)
        self._lock = Lock()
        self._closed = False

    def submit(self, operation: Callable[[], ResultT], *, stage: str) -> Future[ResultT]:
        """中文：非阻塞提交任务，容量耗尽时返回稳定的阶段错误。

        English: Submit without blocking and return a stable stage error when saturated.
        """

        with self._lock:
            if self._closed:
                raise RuntimeError("bounded executor is closed")
        if not self._capacity.acquire(blocking=False):
            raise OperationTimeoutError(
                error_detail(
                    "EXECUTOR_SATURATED",
                    ErrorCategory.TIMEOUT,
                    "The bounded provider executor has no available capacity.",
                    stage=stage,
                )
            )
        try:
            future = self._executor.submit(operation)
        except BaseException:
            self._capacity.release()
            raise
        # 中文：无论成功、异常还是取消，完成回调只释放一次容量。
        # English: The completion callback releases capacity exactly once for every outcome.
        future.add_done_callback(lambda _completed: self._capacity.release())
        return future

    def result(
        self,
        future: Future[ResultT],
        *,
        deadline: DeadlineBudget,
        stage: str,
    ) -> ResultT:
        """中文：按全局剩余预算等待，并在超时后拒收迟到结果。

        English: Wait within global remaining budget and reject late results after timeout.
        """

        # 中文：已完成结果无需消耗剩余预算，可让并行快速分支在另一分支超时后安全降级。
        # English: Completed results consume no remaining wait budget, allowing a fast parallel
        # branch to degrade safely after its sibling times out.
        if future.done():
            return future.result()
        timeout = deadline.timeout_for_call(stage)
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError as exc:
            future.cancel()
            raise OperationTimeoutError(
                error_detail(
                    "STAGE_DEADLINE_EXCEEDED",
                    ErrorCategory.TIMEOUT,
                    "A workflow stage exceeded the remaining deadline.",
                    stage=stage,
                )
            ) from exc

    def shutdown(self, *, wait: bool = False) -> None:
        """中文：停止接收新任务，并默认不等待不可中断的迟到调用。

        English: Stop accepting work and by default do not wait for non-interruptible late calls.
        """

        with self._lock:
            self._closed = True
        self._executor.shutdown(wait=wait, cancel_futures=True)


def run_with_deadline(
    executor: BoundedExecutor,
    operation: Callable[[], ResultT],
    *,
    deadline: DeadlineBudget,
    stage: str,
) -> ResultT:
    """中文：通过同一有界执行器提交并等待一个受截止时间约束的操作。

    English: Submit and await one deadline-bound operation through a shared bounded executor.
    """

    future = executor.submit(operation, stage=stage)
    return executor.result(future, deadline=deadline, stage=stage)
