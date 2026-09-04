"""中文：本模块负责实现“问答服务”相关功能。

English: Pin authorization and index scope before invoking the Agentic RAG state machine.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from enterprise_rag.agent.orchestrator import AgentOrchestrator
from enterprise_rag.agent.state import AgentState
from enterprise_rag.core.enums import ErrorCategory, SnapshotStatus, SourceVisibility
from enterprise_rag.core.exceptions import PermissionDeniedError, RetrievalError, error_detail
from enterprise_rag.core.ids import content_sha256, new_id
from enterprise_rag.domain.models import RetrievalScope, Source, TraceRecord
from enterprise_rag.domain.protocols.observability import TraceRecorder
from enterprise_rag.domain.requests import ChatCommand
from enterprise_rag.domain.results import AnswerResult, RefusalResult
from enterprise_rag.domain.snapshots import KnowledgeSnapshot
from enterprise_rag.infrastructure.persistence.database import transactional_session
from enterprise_rag.infrastructure.persistence.repositories import SQLAlchemyRepositories


class ChatService:
    """中文：该类用于表示或实现“问答服务（ChatService）”的职责。

    English: Create one exact retrieval scope and execute a bounded trusted chat use case.
    """

    def __init__(
        self,
        sessions: sessionmaker[Session],
        orchestrator_factory: Callable[[RetrievalScope], AgentOrchestrator],
        trace_recorder: TraceRecorder,
        timeout_seconds: int,
        snapshot_ttl_seconds: int = 120,
    ) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store metadata, request-pinned agent, tracing, and deadline dependencies.
        """

        # 中文：变量 `_sessions` 用于保存“`sessions`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Session factory reads source ACL and ACTIVE index in one short
        #   transaction.
        self._sessions = sessions
        # 中文：变量 `_orchestrator_factory` 用于保存“编排器工厂”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Factory pins retrieval components to the selected immutable index
        #   version.
        self._orchestrator_factory = orchestrator_factory
        # 中文：变量 `_trace_recorder` 用于保存“追踪记录器”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Recorder receives redacted summaries and must not fail the user workflow.
        self._trace_recorder = trace_recorder
        # 中文：变量 `_timeout_seconds` 用于保存“`timeout``seconds`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Complete workflow wall-clock deadline.
        self._timeout_seconds = timeout_seconds
        # 中文：快照 TTL 限制崩溃请求阻塞物理清理的最长时间。
        # English: Snapshot TTL bounds how long a crashed request may delay physical cleanup.
        self._snapshot_ttl_seconds = snapshot_ttl_seconds

    def chat(self, command: ChatCommand) -> AnswerResult | RefusalResult:
        """中文：该函数或方法负责“问答”相关处理。

        English: Answer within the caller's precomputed source scope and one immutable index.
        """

        # 中文：变量 `scope` 用于保存“范围”相关数据；其精确定义与约束见下方英文说明。
        # English: Scope is computed before any source profile or chunk search.
        scope = self._build_scope(command)
        # 中文：变量 `trace_id` 用于保存“追踪标识符”相关数据；其精确定义与约束见下方英文说明。
        # English: Stable trace ID is generated independently of model and index IDs.
        trace_id = new_id("trc")
        # 中文：变量 `deadline` 用于保存“`deadline`”相关数据；其精确定义与约束见下方英文说明。
        # English: Absolute UTC deadline is checked throughout the agent workflow.
        deadline = datetime.now(UTC) + timedelta(seconds=self._timeout_seconds)
        state = AgentState(
            trace_id=trace_id,
            original_query=command.query,
            current_query=command.query,
            retrieval_scope=scope,
            deadline=deadline,
        )
        # 中文：本步骤涉及追踪、查询，具体约束见下方英文说明。
        # English: Trace summary intentionally excludes the raw query.
        trace_record = TraceRecord(
            id=trace_id,
            tenant_id=command.user.tenant_id,
            user_id=command.user.user_id,
            operation="chat",
            status="started",
            index_version_id=scope.index_version_id,
            snapshot_id=scope.snapshot_id,
            attributes={
                "source_count": len(scope.source_ids),
                "document_version_count": len(scope.document_version_ids),
            },
        )
        with transactional_session(self._sessions) as session:
            SQLAlchemyRepositories(session).add_trace(trace_record)
        self._trace_recorder.start(trace_record)
        try:
            result = self._orchestrator_factory(scope).run(
                state,
                lambda name, attributes: self._trace_recorder.append_step(
                    trace_id,
                    name,
                    attributes,
                ),
            )
            metrics: dict[str, object] = {
                "retrieval_rounds": state.retrieval_rounds,
                "model_call_count": state.model_call_count,
                "token_count": state.token_count,
            }
            self._trace_recorder.finish(
                trace_id,
                state.status.value,
                metrics,
            )
            self._finish_trace(command.user.tenant_id, trace_id, state.status.value, metrics)
            return result
        except Exception:
            metrics = {
                "retrieval_rounds": state.retrieval_rounds,
                "model_call_count": state.model_call_count,
            }
            self._trace_recorder.finish(
                trace_id,
                "error",
                metrics,
            )
            self._finish_trace(command.user.tenant_id, trace_id, "error", metrics)
            raise
        finally:
            if scope.snapshot_id is not None:
                with transactional_session(self._sessions) as session:
                    SQLAlchemyRepositories(session).close_knowledge_snapshot(
                        command.user.tenant_id,
                        scope.snapshot_id,
                        datetime.now(UTC),
                    )

    def _finish_trace(
        self,
        tenant_id: str,
        trace_id: str,
        status: str,
        metrics: dict[str, object],
    ) -> None:
        """中文：把终态和聚合指标写入可授权查询的数据库追踪摘要。

        English: Persist terminal status and aggregates in the authorization-queryable trace
        summary.
        """

        with transactional_session(self._sessions) as session:
            SQLAlchemyRepositories(session).finish_trace(
                tenant_id,
                trace_id,
                status,
                metrics,
            )

    def _build_scope(self, command: ChatCommand) -> RetrievalScope:
        """中文：该内部函数负责“构建范围”相关处理。

        English: Resolve authorized sources and pin the current ACTIVE index version.
        """

        with transactional_session(self._sessions) as session:
            repositories = SQLAlchemyRepositories(session)
            # 中文：变量 `tenant_sources` 用于保存“租户资料源”相关数据；
            # 其精确定义与约束见下方英文说明。
            # English: Candidate sources are tenant-scoped and active before ACL evaluation.
            tenant_sources = tuple(repositories.list_sources(command.user.tenant_id))
            authorized = frozenset(
                source.id for source in tenant_sources if _source_allowed(command, source)
            )
            if command.requested_source_ids:
                # 中文：变量 `unauthorized` 用于保存“`unauthorized`”相关数据；
                # 其精确定义与约束见下方英文说明。
                # English: Explicit unauthorized restrictions are rejected instead of
                #   silently broadened.
                unauthorized = command.requested_source_ids - authorized
                if unauthorized:
                    raise PermissionDeniedError(
                        error_detail(
                            "SOURCE_SCOPE_DENIED",
                            ErrorCategory.PERMISSION,
                            "The requested source scope is not authorized.",
                        )
                    )
                authorized &= command.requested_source_ids
            if not authorized:
                raise PermissionDeniedError(
                    error_detail(
                        "NO_AUTHORIZED_SOURCES",
                        ErrorCategory.PERMISSION,
                        "The user has no authorized active knowledge sources.",
                    )
                )
            active_index = repositories.get_active_index(command.user.tenant_id)
            if active_index is None:
                raise RetrievalError(
                    error_detail(
                        "ACTIVE_INDEX_NOT_FOUND",
                        ErrorCategory.RETRIEVAL,
                        "No active knowledge index is available for this tenant.",
                    )
                )
            active_versions = tuple(repositories.list_active_versions(command.user.tenant_id))
            pinned_version_ids = frozenset(
                version.id for version in active_versions if version.source_id in authorized
            )
            if not pinned_version_ids:
                raise RetrievalError(
                    error_detail(
                        "AUTHORIZED_DOCUMENT_VERSION_NOT_FOUND",
                        ErrorCategory.RETRIEVAL,
                        "No active document version is available in the authorized scope.",
                    )
                )
            snapshot_id = new_id("snp")
            created_at = datetime.now(UTC)
            scope = RetrievalScope(
                tenant_id=command.user.tenant_id,
                source_ids=authorized,
                index_version_id=active_index.id,
                document_version_ids=pinned_version_ids,
                snapshot_id=snapshot_id,
            )
            authorization_fingerprint = content_sha256(
                "\0".join(
                    (
                        command.user.user_id,
                        *sorted(command.user.roles),
                        *sorted(command.user.group_ids),
                        *sorted(authorized),
                    )
                )
            )
            snapshot = KnowledgeSnapshot(
                id=snapshot_id,
                tenant_id=command.user.tenant_id,
                user_id=command.user.user_id,
                status=SnapshotStatus.ACTIVE,
                index_version_id=active_index.id,
                index_manifest_fingerprint=(active_index.config_fingerprint or active_index.id),
                source_ids=authorized,
                document_version_ids=pinned_version_ids,
                authorization_fingerprint=authorization_fingerprint,
                captured_revocation_epoch=repositories.current_revocation_epoch(
                    command.user.tenant_id
                ),
                created_at=created_at,
                expires_at=created_at + timedelta(seconds=self._snapshot_ttl_seconds),
            )
            repositories.add_knowledge_snapshot(
                snapshot,
                {
                    version.id: version.source_id
                    for version in active_versions
                    if version.id in pinned_version_ids
                },
            )
            return scope


def _source_allowed(command: ChatCommand, source: Source) -> bool:
    """中文：该内部函数负责“资料源允许的”相关处理。

    English: Return whether trusted roles, explicit grants, and groups permit one source.
    """

    user = command.user
    if user.is_admin():
        return True
    if source.id in user.allowed_source_ids:
        return True
    if source.visibility is SourceVisibility.TENANT:
        return True
    if source.visibility is SourceVisibility.RESTRICTED:
        return bool(source.allowed_group_ids & user.group_ids)
    return False
