"""中文：本模块为长时间资料接入任务提供租约心跳、检查点与 fencing 失效保护。

English: Provide lease heartbeats, checkpoints, and fencing-loss protection for long-running
ingestion jobs.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Event, Lock, Thread
from types import TracebackType

from sqlalchemy.orm import Session, sessionmaker

from enterprise_rag.core.enums import ErrorCategory
from enterprise_rag.core.exceptions import LeaseLostError, error_detail
from enterprise_rag.domain.models import JobFence
from enterprise_rag.infrastructure.persistence.database import transactional_session
from enterprise_rag.infrastructure.persistence.repositories import SQLAlchemyRepositories


class JobLeaseGuard:
    """中文：在耗时 OCR、Embedding 与索引构建期间持续维护任务所有权。

    English: Maintain job ownership during expensive OCR, embedding, and index construction.
    """

    def __init__(
        self,
        sessions: sessionmaker[Session],
        fence: JobFence,
        lease_seconds: int,
        heartbeat_seconds: int,
    ) -> None:
        """中文：保存会话工厂、fencing token 和经过校验的心跳时间参数。

        English: Store the session factory, fencing token, and validated heartbeat timings.
        """

        if lease_seconds < 1:
            raise ValueError("lease duration must be positive")
        if not 0 < heartbeat_seconds < lease_seconds:
            raise ValueError("heartbeat interval must be shorter than the lease duration")
        # 中文：关键变量 `_sessions` 让心跳线程每次使用独立数据库 Session。
        # English: Key variable `_sessions` gives every heartbeat an independent DB session.
        self._sessions = sessions
        # 中文：关键变量 `_fence` 固定本轮 Worker 的 owner 与 attempt generation。
        # English: Key variable `_fence` pins the worker owner and attempt generation.
        self._fence = fence
        # 中文：关键变量 `_lease_seconds` 决定每次成功续租后的新到期时间。
        # English: Key variable `_lease_seconds` determines the renewed expiration deadline.
        self._lease_seconds = lease_seconds
        # 中文：关键变量 `_heartbeat_seconds` 决定后台续租频率。
        # English: Key variable `_heartbeat_seconds` controls background renewal frequency.
        self._heartbeat_seconds = heartbeat_seconds
        # 中文：停止事件允许主 Worker 及时结束守护线程。
        # English: The stop event lets the main worker terminate the guard promptly.
        self._stop_event = Event()
        # 中文：失租事件跨线程传播不可恢复的任务所有权丢失。
        # English: The lost event propagates irreversible ownership loss across threads.
        self._lease_lost_event = Event()
        # 中文：状态锁保护错误原因和线程引用的并发访问。
        # English: The state lock protects the error reason and thread reference.
        self._state_lock = Lock()
        self._failure_reason = "lease renewal was rejected"
        self._thread: Thread | None = None

    def __enter__(self) -> JobLeaseGuard:
        """中文：验证初始租约并启动后台心跳。

        English: Verify the initial lease and start the background heartbeat.
        """

        self.checkpoint()
        self.start()
        return self

    def __exit__(
        self,
        _: type[BaseException] | None,
        __: BaseException | None,
        ___: TracebackType | None,
    ) -> None:
        """中文：无论任务成功或失败都停止心跳线程。

        English: Stop the heartbeat thread after either success or failure.
        """

        self.stop()

    def start(self) -> None:
        """中文：幂等启动一个守护线程执行周期性数据库续租。

        English: Idempotently start one daemon thread for periodic database renewals.
        """

        with self._state_lock:
            if self._thread is not None:
                return
            # 中文：关键变量 `_thread` 使用守护模式，避免异常退出时阻塞进程关闭。
            # English: Key variable `_thread` is a daemon so abnormal shutdown cannot hang.
            self._thread = Thread(
                target=self._heartbeat_loop,
                name=f"job-lease-{self._fence.job_id}",
                daemon=True,
            )
            self._thread.start()

    def checkpoint(self) -> None:
        """中文：在每个持久化或发布阶段前同步验证 fencing token。

        English: Synchronize and verify the fencing token before persistence or publication.
        """

        self._raise_if_lost()
        now = datetime.now(UTC)
        try:
            with transactional_session(self._sessions) as session:
                SQLAlchemyRepositories(session).assert_job_fence(self._fence, now)
        except LeaseLostError:
            self._record_lease_loss("the synchronous fencing checkpoint was rejected")
            raise

    def stop(self) -> None:
        """中文：通知心跳线程退出并在有限时间内等待其完成。

        English: Signal the heartbeat thread and join it for a bounded interval.
        """

        self._stop_event.set()
        with self._state_lock:
            thread = self._thread
        if thread is not None:
            thread.join(timeout=float(self._heartbeat_seconds + 1))

    def _heartbeat_loop(self) -> None:
        """中文：周期性续租；数据库异常或条件更新失败都立即使 fencing 失效。

        English: Renew periodically; database errors or rejected updates invalidate the fence.
        """

        while not self._stop_event.wait(self._heartbeat_seconds):
            now = datetime.now(UTC)
            try:
                with transactional_session(self._sessions) as session:
                    renewed = SQLAlchemyRepositories(session).renew_job_lease(
                        self._fence,
                        now,
                        now + timedelta(seconds=self._lease_seconds),
                    )
                if not renewed:
                    self._record_lease_loss("the background lease renewal was rejected")
                    return
            except Exception:
                # 中文：数据库不可达时不能假定仍持有租约，安全策略是停止一切后续提交。
                # English: A database outage cannot prove ownership, so all later commits stop.
                self._record_lease_loss("the background lease renewal failed")
                return

    def _record_lease_loss(self, reason: str) -> None:
        """中文：原子记录首次失租原因并通知主 Worker。

        English: Record the first lease-loss reason atomically and notify the main worker.
        """

        with self._state_lock:
            if not self._lease_lost_event.is_set():
                self._failure_reason = reason
                self._lease_lost_event.set()

    def _raise_if_lost(self) -> None:
        """中文：若后台心跳已失败，则抛出安全的领域冲突错误。

        English: Raise a safe domain conflict when the background heartbeat has failed.
        """

        if not self._lease_lost_event.is_set():
            return
        raise LeaseLostError(
            error_detail(
                "INGESTION_LEASE_LOST",
                ErrorCategory.CONFLICT,
                "The ingestion worker no longer owns this job attempt.",
                job_id=self._fence.job_id,
                reason=self._failure_reason,
            )
        )
