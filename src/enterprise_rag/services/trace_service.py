"""中文：本模块负责实现“追踪服务”相关功能。

English: Return redacted trace summaries only to their owner or a tenant administrator.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from enterprise_rag.core.enums import ErrorCategory
from enterprise_rag.core.exceptions import NotFoundError, error_detail
from enterprise_rag.domain.models import UserContext
from enterprise_rag.domain.results import TraceView
from enterprise_rag.infrastructure.persistence.database import transactional_session
from enterprise_rag.infrastructure.persistence.repositories import SQLAlchemyRepositories


class TraceService:
    """中文：该类用于表示或实现“追踪服务（TraceService）”的职责。

    English: Apply tenant and ownership checks before exposing safe trace attributes.
    """

    def __init__(
        self,
        sessions: sessionmaker[Session],
        trace_root: Path | None = None,
    ) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store the metadata session factory.
        """

        # 中文：变量 `_sessions` 用于保存“`sessions`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: One read transaction handles each trace query.
        self._sessions = sessions
        # 中文：变量 `_trace_root` 仅用于读取已授权追踪的脱敏追加事件。
        # English: `_trace_root` reads redacted append-only events only after authorization.
        self._trace_root = trace_root.expanduser().resolve() if trace_root is not None else None

    def get(self, user: UserContext, trace_id: str) -> TraceView:
        """中文：该函数或方法负责“读取目标对象”相关处理。

        English: Return a redacted trace view without disclosing cross-user existence.
        """

        with transactional_session(self._sessions) as session:
            trace = SQLAlchemyRepositories(session).get_trace(user.tenant_id, trace_id)
            if trace is None or (not user.is_admin() and trace.user_id != user.user_id):
                raise NotFoundError(
                    error_detail(
                        "TRACE_NOT_FOUND",
                        ErrorCategory.NOT_FOUND,
                        "The trace does not exist.",
                    )
                )
            metrics = {
                key: value
                for key, value in trace.attributes.items()
                if isinstance(value, (int, float, str))
            }
            return TraceView(
                trace_id=trace.id,
                status=trace.status,
                steps=self._load_steps(trace.id),
                metrics=metrics,
            )

    def _load_steps(self, trace_id: str) -> tuple[dict[str, object], ...]:
        """中文：从租户授权后的单个 JSONL 文件读取有序脱敏步骤。

        English: Read ordered redacted steps from one JSONL file after tenant authorization.
        """

        if self._trace_root is None or any(character in trace_id for character in ("/", "\\")):
            return ()
        target = (self._trace_root / f"{trace_id}.jsonl").resolve()
        try:
            target.relative_to(self._trace_root)
            lines = target.read_text(encoding="utf-8").splitlines()
        except (OSError, ValueError):
            return ()
        steps: list[dict[str, object]] = []
        for line in lines:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict) or payload.get("event") != "step":
                continue
            step = payload.get("step")
            if isinstance(step, dict):
                steps.append({str(key): value for key, value in step.items()})
        return tuple(steps)
