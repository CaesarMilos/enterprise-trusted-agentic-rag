"""中文：本模块负责实现“仓储”相关功能。

English: Implement tenant-scoped domain repositories with one caller-owned SQLAlchemy session.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from enterprise_rag.core.enums import (
    ContentProfile,
    DocumentStatus,
    ErrorCategory,
    IndexStatus,
    JobStatus,
    SourceVisibility,
)
from enterprise_rag.core.exceptions import (
    JobCancelledError,
    LeaseLostError,
    LifecycleFenceError,
    StaleIndexBuildPlanError,
    error_detail,
)
from enterprise_rag.core.state_machine import (
    DOCUMENT_TRANSITIONS,
    INDEX_TRANSITIONS,
    ensure_transition,
)
from enterprise_rag.domain.models import (
    Chunk,
    Document,
    DocumentVersion,
    IndexVersion,
    IngestionJob,
    JobFence,
    Source,
    TraceRecord,
    utc_now,
)
from enterprise_rag.infrastructure.persistence.orm_models import (
    ChunkRow,
    DocumentRow,
    DocumentVersionRow,
    IndexVersionRow,
    IngestionJobRow,
    SourceRow,
    TenantRow,
    TraceRow,
)

# 中文：哨兵区分“未启用乐观校验”和“期望当前没有活动索引”。
# English: Sentinel distinguishes disabled optimistic checks from expecting no active index.
_UNSET_ACTIVE_INDEX = object()


def _rowcount(result: object) -> int:
    """中文：安全读取 SQLAlchemy DML 影响行数，并兼容其抽象 Result 类型标注。

    English: Safely read DML affected rows while accommodating SQLAlchemy's abstract Result type.
    """

    value = getattr(result, "rowcount", 0)
    return value if isinstance(value, int) else 0


class SQLAlchemyRepositories:
    """中文：该类用于表示或实现“SQLAlchemy仓储（SQLAlchemyRepositories）”的职责。

    English: Provide all repository ports over one explicit application transaction.
    """

    def __init__(self, session: Session) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Bind repository operations to the caller-owned transaction.
        """

        # 中文：变量 `_session` 用于保存“会话”相关数据；其精确定义与约束见下方英文说明。
        # English: Session is intentionally not committed or closed by repository methods.
        self._session = session

    def add_source(self, source: Source) -> None:
        """中文：该函数或方法负责“新增资料源”相关处理。

        English: Persist a new routable source.
        """

        self._session.add(
            SourceRow(
                id=source.id,
                tenant_id=source.tenant_id,
                name=source.name,
                description=source.description,
                content_profile=source.content_profile.value,
                chunk_strategy_override=source.chunk_strategy_override,
                visibility=source.visibility.value,
                allowed_group_ids=sorted(source.allowed_group_ids),
                is_active=source.is_active,
                created_at=source.created_at,
            )
        )
        self._session.flush()

    def get_source(self, tenant_id: str, source_id: str) -> Source | None:
        """中文：该函数或方法负责“获取资料源”相关处理。

        English: Return a source only when both its tenant and identifier match.
        """

        # 中文：变量 `row` 用于保存“`row`”相关数据；其精确定义与约束见下方英文说明。
        # English: Tenant predicate prevents cross-tenant existence disclosure.
        row = self._session.scalar(
            select(SourceRow).where(
                SourceRow.tenant_id == tenant_id,
                SourceRow.id == source_id,
            )
        )
        return _source_from_row(row) if row is not None else None

    def list_authorized_sources(
        self,
        tenant_id: str,
        source_ids: frozenset[str],
    ) -> Sequence[Source]:
        """中文：该函数或方法负责“列出已授权资料源”相关处理。

        English: Return active tenant sources intersected with an explicit allow-list.
        """

        if not source_ids:
            return ()
        # 中文：变量 `rows` 用于保存“`rows`”相关数据；其精确定义与约束见下方英文说明。
        # English: Query applies tenancy, activity, and explicit authorization before
        #   returning profiles.
        rows = self._session.scalars(
            select(SourceRow)
            .where(
                SourceRow.tenant_id == tenant_id,
                SourceRow.is_active.is_(True),
                SourceRow.id.in_(source_ids),
            )
            .order_by(SourceRow.name, SourceRow.id)
        ).all()
        return tuple(_source_from_row(row) for row in rows)

    def list_sources(self, tenant_id: str, active_only: bool = True) -> Sequence[Source]:
        """中文：该函数或方法负责“列出资料源”相关处理。

        English: Return tenant sources with an optional activity filter.
        """

        # 中文：变量 `statement` 用于保存“`statement`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Base query always applies tenant isolation.
        statement = select(SourceRow).where(SourceRow.tenant_id == tenant_id)
        if active_only:
            statement = statement.where(SourceRow.is_active.is_(True))
        rows = self._session.scalars(statement.order_by(SourceRow.name, SourceRow.id)).all()
        return tuple(_source_from_row(row) for row in rows)

    def update_source_content_profile(
        self,
        tenant_id: str,
        source_id: str,
        content_profile: ContentProfile,
        chunk_strategy_override: str | None = None,
    ) -> Source | None:
        """中文：更新资料源内容画像并返回新的不可变领域对象。

        English: Update a source content profile and return the refreshed immutable entity.
        """

        # 中文：变量 `row` 仅在租户与资料源标识同时匹配时返回，防止越权更新。
        # English: The row is returned only for an exact tenant/source match.
        row = self._session.scalar(
            select(SourceRow).where(
                SourceRow.tenant_id == tenant_id,
                SourceRow.id == source_id,
            )
        )
        if row is None:
            return None
        row.content_profile = content_profile.value
        row.chunk_strategy_override = chunk_strategy_override
        self._session.flush()
        return _source_from_row(row)

    def add_document(self, document: Document) -> None:
        """中文：该函数或方法负责“新增文档”相关处理。

        English: Persist a logical document lifecycle record.
        """

        self._session.add(
            DocumentRow(
                id=document.id,
                tenant_id=document.tenant_id,
                source_id=document.source_id,
                title=document.title,
                status=document.status.value,
                active_version_id=document.active_version_id,
                lifecycle_generation=document.lifecycle_generation,
                delete_requested_at=document.delete_requested_at,
                deleted_at=document.deleted_at,
                created_at=document.created_at,
                updated_at=document.updated_at,
            )
        )
        self._session.flush()

    def add_version(self, version: DocumentVersion) -> None:
        """中文：该函数或方法负责“新增版本”相关处理。

        English: Persist immutable original-file metadata for a document version.
        """

        self._session.add(
            DocumentVersionRow(
                id=version.id,
                tenant_id=version.tenant_id,
                document_id=version.document_id,
                source_id=version.source_id,
                version_number=version.version_number,
                original_filename=version.original_filename,
                media_type=version.media_type,
                content_hash=version.content_hash,
                storage_key=version.storage_key,
                size_bytes=version.size_bytes,
                ingestion_snapshot={
                    "content_profile": version.content_profile.value,
                    "chunk_strategy_id": version.chunk_strategy_id,
                    "chunk_strategy_version": version.chunk_strategy_version,
                    "chunk_parameters": version.chunk_parameters,
                    "embedding_fingerprint": version.embedding_fingerprint,
                    "boundary_model_fingerprint": version.boundary_model_fingerprint,
                    "profile_confidence": version.profile_confidence,
                    "tokenizer_id": version.tokenizer_id,
                    "extraction_pipeline_version": version.extraction_pipeline_version,
                    "quality_metrics": version.quality_metrics,
                },
                created_at=version.created_at,
            )
        )
        self._session.flush()

    def get_document(self, tenant_id: str, document_id: str) -> Document | None:
        """中文：该函数或方法负责“获取文档”相关处理。

        English: Return a logical document only inside the requested tenant.
        """

        # 中文：变量 `row` 用于保存“`row`”相关数据；其精确定义与约束见下方英文说明。
        # English: Tenant predicate is mandatory even though document IDs are globally
        #   unique.
        row = self._session.scalar(
            select(DocumentRow).where(
                DocumentRow.tenant_id == tenant_id,
                DocumentRow.id == document_id,
            )
        )
        return _document_from_row(row) if row is not None else None

    def get_version(self, tenant_id: str, version_id: str) -> DocumentVersion | None:
        """中文：该函数或方法负责“获取版本”相关处理。

        English: Return an immutable document version only inside the requested tenant.
        """

        row = self._session.scalar(
            select(DocumentVersionRow).where(
                DocumentVersionRow.tenant_id == tenant_id,
                DocumentVersionRow.id == version_id,
            )
        )
        return _version_from_row(row) if row is not None else None

    def next_version_number(self, tenant_id: str, document_id: str) -> int:
        """中文：该函数或方法负责“下一个版本编号”相关处理。

        English: Return the next monotonic version number for one tenant-owned document.
        """

        # 中文：变量 `latest` 用于保存“`latest`”相关数据；其精确定义与约束见下方英文说明。
        # English: Ordered query avoids database-specific aggregate type handling.
        latest = self._session.scalar(
            select(DocumentVersionRow)
            .where(
                DocumentVersionRow.tenant_id == tenant_id,
                DocumentVersionRow.document_id == document_id,
            )
            .order_by(DocumentVersionRow.version_number.desc())
            .limit(1)
        )
        return 1 if latest is None else latest.version_number + 1

    def set_document_status(
        self,
        tenant_id: str,
        document_id: str,
        status: DocumentStatus,
        active_version_id: str | None = None,
        expected_generation: int | None = None,
    ) -> None:
        """中文：该函数或方法负责“设置文档状态”相关处理。

        English: Update document state and optionally its active immutable version.
        """

        row = self._session.scalar(
            select(DocumentRow)
            .where(
                DocumentRow.tenant_id == tenant_id,
                DocumentRow.id == document_id,
            )
            .with_for_update()
        )
        if row is None:
            raise LifecycleFenceError(
                error_detail(
                    "DOCUMENT_LIFECYCLE_FENCE_REJECTED",
                    ErrorCategory.CONFLICT,
                    "The document no longer exists.",
                    document_id=document_id,
                )
            )
        current_status = DocumentStatus(row.status)
        ensure_transition(current_status, status, DOCUMENT_TRANSITIONS)
        # 中文：变量 `values` 保存状态和可选活动版本，并与读取到的当前状态做 CAS。
        # English: Update mapping preserves the active version and state-CASes the current row.
        values: dict[str, object] = {"status": status.value, "updated_at": utc_now()}
        if active_version_id is not None:
            values["active_version_id"] = active_version_id
        statement = update(DocumentRow).where(
            DocumentRow.tenant_id == tenant_id,
            DocumentRow.id == document_id,
            DocumentRow.status == current_status.value,
        )
        # 中文：普通处理结果永远不能把删除中的文档恢复为 READY 或 FAILED。
        # English: Ordinary processing results can never revive a deleting document.
        if status not in {DocumentStatus.PENDING_DELETE, DocumentStatus.DELETED}:
            statement = statement.where(
                DocumentRow.status.not_in(
                    (DocumentStatus.PENDING_DELETE.value, DocumentStatus.DELETED.value)
                )
            )
        if expected_generation is not None:
            statement = statement.where(DocumentRow.lifecycle_generation == expected_generation)
        result = self._session.execute(statement.values(**values))
        if _rowcount(result) != 1:
            raise LifecycleFenceError(
                error_detail(
                    "DOCUMENT_LIFECYCLE_FENCE_REJECTED",
                    ErrorCategory.CONFLICT,
                    "The document lifecycle changed before this update could commit.",
                    document_id=document_id,
                )
            )
        self._session.flush()

    def request_document_deletion(
        self,
        tenant_id: str,
        document_id: str,
        now: datetime,
        reason: str = "document_deleted",
    ) -> Document | None:
        """中文：原子递增 generation、进入删除态并取消所有未完成任务。

        English: Atomically increment generation, enter deletion state, and cancel unfinished jobs.
        """

        row = self._session.scalar(
            select(DocumentRow)
            .where(DocumentRow.tenant_id == tenant_id, DocumentRow.id == document_id)
            .with_for_update()
        )
        if row is None:
            return None
        if row.status == DocumentStatus.DELETED.value:
            return _document_from_row(row)
        if row.status != DocumentStatus.PENDING_DELETE.value:
            row.status = DocumentStatus.PENDING_DELETE.value
            row.lifecycle_generation += 1
            row.delete_requested_at = now
            row.updated_at = now
        # 中文：排队任务立即取消；运行任务设置持久标志，由 Worker 在检查点安全停止。
        # English: Pending jobs cancel now; running workers stop at durable checkpoints.
        self._session.execute(
            update(IngestionJobRow)
            .where(
                IngestionJobRow.tenant_id == tenant_id,
                IngestionJobRow.document_id == document_id,
                IngestionJobRow.status == JobStatus.PENDING.value,
            )
            .values(
                status=JobStatus.CANCELLED.value,
                cancel_requested_at=now,
                cancel_reason=reason,
                updated_at=now,
            )
        )
        self._session.execute(
            update(IngestionJobRow)
            .where(
                IngestionJobRow.tenant_id == tenant_id,
                IngestionJobRow.document_id == document_id,
                IngestionJobRow.status == JobStatus.RUNNING.value,
            )
            .values(cancel_requested_at=now, cancel_reason=reason, updated_at=now)
        )
        self._session.flush()
        return _document_from_row(row)

    def complete_document_deletion(
        self,
        tenant_id: str,
        document_id: str,
        generation: int,
        now: datetime,
    ) -> None:
        """中文：仅在相同删除 generation 下完成删除并清除活动版本引用。

        English: Complete deletion and clear active version only for the same generation.
        """

        result = self._session.execute(
            update(DocumentRow)
            .where(
                DocumentRow.tenant_id == tenant_id,
                DocumentRow.id == document_id,
                DocumentRow.status == DocumentStatus.PENDING_DELETE.value,
                DocumentRow.lifecycle_generation == generation,
            )
            .values(
                status=DocumentStatus.DELETED.value,
                active_version_id=None,
                deleted_at=now,
                updated_at=now,
            )
        )
        if _rowcount(result) != 1:
            raise LifecycleFenceError(
                error_detail(
                    "DOCUMENT_DELETE_FENCE_REJECTED",
                    ErrorCategory.CONFLICT,
                    "The deletion generation no longer matches the document.",
                    document_id=document_id,
                )
            )
        self._session.flush()

    def list_active_versions(self, tenant_id: str) -> Sequence[DocumentVersion]:
        """中文：该函数或方法负责“列出活动版本”相关处理。

        English: Return immutable versions currently activated by ready logical documents.
        """

        # 中文：变量 `rows` 用于保存“`rows`”相关数据；其精确定义与约束见下方英文说明。
        # English: The active-version join excludes historical, failed, pending-delete,
        #   and deleted content.
        rows = self._session.scalars(
            select(DocumentVersionRow)
            .join(
                DocumentRow,
                DocumentRow.active_version_id == DocumentVersionRow.id,
            )
            .join(
                SourceRow,
                (SourceRow.id == DocumentVersionRow.source_id)
                & (SourceRow.tenant_id == DocumentVersionRow.tenant_id),
            )
            .where(
                DocumentRow.tenant_id == tenant_id,
                DocumentRow.status == DocumentStatus.READY.value,
                DocumentVersionRow.tenant_id == tenant_id,
                SourceRow.is_active.is_(True),
            )
            .order_by(DocumentVersionRow.id)
        ).all()
        return tuple(_version_from_row(row) for row in rows)

    def replace_version_chunks(
        self,
        tenant_id: str,
        document_version_id: str,
        chunks: Sequence[Chunk],
    ) -> None:
        """中文：该函数或方法负责“`replace`版本文本块”相关处理。

        English: Replace all chunks for an immutable version within the current transaction.
        """

        # 中文：本步骤涉及活动、输出，具体约束见下方英文说明。
        # English: Existing non-active attempt output is removed before deterministic
        #   recreation.
        self._session.execute(
            delete(ChunkRow).where(
                ChunkRow.tenant_id == tenant_id,
                ChunkRow.document_version_id == document_version_id,
            )
        )
        # 中文：本步骤涉及文本块、事务、范围，具体约束见下方英文说明。
        # English: Every supplied chunk must match the explicit transaction scope.
        for chunk in chunks:
            if chunk.tenant_id != tenant_id or chunk.document_version_id != document_version_id:
                raise ValueError("chunk scope does not match replacement scope")
            self._session.add(_chunk_to_row(chunk))
        self._session.flush()

    def update_version_quality_metrics(
        self,
        tenant_id: str,
        document_version_id: str,
        metrics: dict[str, object],
        warnings: tuple[str, ...],
    ) -> None:
        """中文：把质量门指标与警告合并进不可变版本的接入审计快照。

        English: Merge quality-gate metrics and warnings into the immutable version audit
        snapshot.
        """

        row = self._session.scalar(
            select(DocumentVersionRow).where(
                DocumentVersionRow.tenant_id == tenant_id,
                DocumentVersionRow.id == document_version_id,
            )
        )
        if row is None:
            raise ValueError("document version does not exist in the requested tenant")
        snapshot = _json_mapping(row.ingestion_snapshot)
        snapshot["quality_metrics"] = metrics
        snapshot["quality_warnings"] = list(warnings)
        row.ingestion_snapshot = snapshot
        self._session.flush()

    def list_active_chunks(self, tenant_id: str) -> Sequence[Chunk]:
        """中文：该函数或方法负责“列出活动文本块”相关处理。

        English: Return chunks belonging only to ready documents' active versions.
        """

        rows = self._session.scalars(
            select(ChunkRow)
            .join(DocumentRow, DocumentRow.active_version_id == ChunkRow.document_version_id)
            .join(
                SourceRow,
                (SourceRow.id == ChunkRow.source_id)
                & (SourceRow.tenant_id == ChunkRow.tenant_id),
            )
            .where(
                ChunkRow.tenant_id == tenant_id,
                DocumentRow.tenant_id == tenant_id,
                DocumentRow.status == DocumentStatus.READY.value,
                SourceRow.is_active.is_(True),
            )
            .order_by(ChunkRow.document_id, ChunkRow.ordinal)
        ).all()
        return tuple(_chunk_from_row(row) for row in rows)

    def get_chunks(self, tenant_id: str, chunk_ids: Sequence[str]) -> Sequence[Chunk]:
        """中文：以安全默认语义返回当前可进入在线检索的 Chunk。

        English: Return currently retrievable chunks with secure-by-default semantics.
        """

        return self.get_retrievable_chunks(tenant_id, chunk_ids)

    def get_retrievable_chunks(
        self,
        tenant_id: str,
        chunk_ids: Sequence[str],
    ) -> Sequence[Chunk]:
        """中文：只返回当前 READY 文档活动版本且资料源仍启用的在线 Chunk。

        English: Return only chunks from active READY document versions and enabled sources.
        """

        if not chunk_ids:
            return ()
        # 中文：关键变量 `rows` 以数据库生命周期状态作为旧索引之后的最终撤销边界。
        # English: Key variable `rows` makes database lifecycle state the final revocation
        # boundary after a stale index returns candidate identifiers.
        rows = self._session.scalars(
            select(ChunkRow)
            .join(
                DocumentRow,
                (DocumentRow.id == ChunkRow.document_id)
                & (DocumentRow.tenant_id == ChunkRow.tenant_id),
            )
            .join(
                SourceRow,
                (SourceRow.id == ChunkRow.source_id)
                & (SourceRow.tenant_id == ChunkRow.tenant_id),
            )
            .where(
                ChunkRow.tenant_id == tenant_id,
                ChunkRow.id.in_(chunk_ids),
                DocumentRow.status == DocumentStatus.READY.value,
                DocumentRow.active_version_id == ChunkRow.document_version_id,
                SourceRow.is_active.is_(True),
            )
        ).all()
        by_id = {row.id: _chunk_from_row(row) for row in rows}
        return tuple(by_id[chunk_id] for chunk_id in chunk_ids if chunk_id in by_id)

    def list_version_chunks(
        self,
        tenant_id: str,
        document_version_id: str,
    ) -> Sequence[Chunk]:
        """中文：该函数或方法负责“列出版本文本块”相关处理。

        English: Return every chunk for one tenant-owned immutable document version.
        """

        rows = self._session.scalars(
            select(ChunkRow)
            .where(
                ChunkRow.tenant_id == tenant_id,
                ChunkRow.document_version_id == document_version_id,
            )
            .order_by(ChunkRow.ordinal)
        ).all()
        return tuple(_chunk_from_row(row) for row in rows)

    def add_job(self, job: IngestionJob) -> None:
        """中文：该函数或方法负责“新增任务”相关处理。

        English: Persist a durable pending ingestion job.
        """

        self._session.add(
            IngestionJobRow(
                id=job.id,
                tenant_id=job.tenant_id,
                document_id=job.document_id,
                document_version_id=job.document_version_id,
                document_generation_snapshot=job.document_generation_snapshot,
                status=job.status.value,
                attempt_count=job.attempt_count,
                lease_owner=job.lease_owner,
                lease_expires_at=job.lease_expires_at,
                error_code=job.error_code,
                error_message=job.error_message,
                cancel_requested_at=job.cancel_requested_at,
                cancel_reason=job.cancel_reason,
                created_at=job.created_at,
                updated_at=job.updated_at,
            )
        )
        self._session.flush()

    def get_job(self, tenant_id: str, job_id: str) -> IngestionJob | None:
        """中文：该函数或方法负责“获取任务”相关处理。

        English: Return a durable job only inside the requested tenant.
        """

        row = self._session.scalar(
            select(IngestionJobRow).where(
                IngestionJobRow.tenant_id == tenant_id,
                IngestionJobRow.id == job_id,
            )
        )
        return _job_from_row(row) if row is not None else None

    def claim_next_job(
        self,
        worker_id: str,
        now: datetime,
        lease_until: datetime,
    ) -> IngestionJob | None:
        """中文：该函数或方法负责“领取下一个任务”相关处理。

        English: Claim the oldest pending or expired running job in the current transaction.
        """

        # 中文：先只选择候选 ID，随后用带状态条件的单条 UPDATE 原子竞争租约。
        # English: Select only a candidate ID, then compete for its lease with one conditional
        # atomic UPDATE that also works on SQLite.
        candidate_id = self._session.scalar(
            select(IngestionJobRow.id)
            .where(
                IngestionJobRow.cancel_requested_at.is_(None),
                or_(
                    IngestionJobRow.status == JobStatus.PENDING.value,
                    (
                        (IngestionJobRow.status == JobStatus.RUNNING.value)
                        & (IngestionJobRow.lease_expires_at < now)
                    ),
                )
            )
            .order_by(IngestionJobRow.created_at, IngestionJobRow.id)
            .limit(1)
        )
        if candidate_id is None:
            return None
        claim_result = self._session.execute(
            update(IngestionJobRow)
            .where(
                IngestionJobRow.id == candidate_id,
                IngestionJobRow.cancel_requested_at.is_(None),
                or_(
                    IngestionJobRow.status == JobStatus.PENDING.value,
                    (
                        (IngestionJobRow.status == JobStatus.RUNNING.value)
                        & (IngestionJobRow.lease_expires_at < now)
                    ),
                ),
            )
            .values(
                status=JobStatus.RUNNING.value,
                lease_owner=worker_id,
                lease_expires_at=lease_until,
                attempt_count=IngestionJobRow.attempt_count + 1,
                updated_at=now,
            )
        )
        if _rowcount(claim_result) != 1:
            return None
        self._session.flush()
        candidate = self._session.scalar(
            select(IngestionJobRow).where(IngestionJobRow.id == candidate_id)
        )
        if candidate is None:
            return None
        return _job_from_row(candidate)

    def renew_job_lease(
        self,
        fence: JobFence,
        now: datetime,
        lease_until: datetime,
    ) -> bool:
        """中文：仅由仍持有相同 fencing generation 的 Worker 续租任务。

        English: Renew a job only for the worker that still owns the same fencing generation.
        """

        if lease_until <= now:
            raise ValueError("renewed lease must expire after the renewal time")
        result = self._session.execute(
            update(IngestionJobRow)
            .where(
                IngestionJobRow.tenant_id == fence.tenant_id,
                IngestionJobRow.id == fence.job_id,
                IngestionJobRow.status == JobStatus.RUNNING.value,
                IngestionJobRow.lease_owner == fence.lease_owner,
                IngestionJobRow.attempt_count == fence.attempt_count,
                IngestionJobRow.lease_expires_at.is_not(None),
                IngestionJobRow.lease_expires_at > now,
                IngestionJobRow.cancel_requested_at.is_(None),
                IngestionJobRow.document_generation_snapshot == fence.document_generation,
                IngestionJobRow.document_id.in_(
                    select(DocumentRow.id).where(
                        DocumentRow.tenant_id == fence.tenant_id,
                        DocumentRow.id == fence.document_id,
                        DocumentRow.lifecycle_generation == fence.document_generation,
                        DocumentRow.status.not_in(
                            (DocumentStatus.PENDING_DELETE.value, DocumentStatus.DELETED.value)
                        ),
                    )
                ),
            )
            .values(lease_expires_at=lease_until, updated_at=now)
        )
        self._session.flush()
        return _rowcount(result) == 1

    def assert_job_fence(self, fence: JobFence, now: datetime) -> None:
        """中文：在副作用事务内锁定并验证当前 Worker 的有效租约代次。

        English: Lock and verify the worker's live lease generation inside a side-effect
        transaction.
        """

        result = self._session.execute(
            update(IngestionJobRow)
            .where(
                IngestionJobRow.tenant_id == fence.tenant_id,
                IngestionJobRow.id == fence.job_id,
                IngestionJobRow.status == JobStatus.RUNNING.value,
                IngestionJobRow.lease_owner == fence.lease_owner,
                IngestionJobRow.attempt_count == fence.attempt_count,
                IngestionJobRow.lease_expires_at.is_not(None),
                IngestionJobRow.lease_expires_at > now,
                IngestionJobRow.cancel_requested_at.is_(None),
                IngestionJobRow.document_generation_snapshot == fence.document_generation,
                IngestionJobRow.document_id.in_(
                    select(DocumentRow.id).where(
                        DocumentRow.tenant_id == fence.tenant_id,
                        DocumentRow.id == fence.document_id,
                        DocumentRow.lifecycle_generation == fence.document_generation,
                        DocumentRow.status.not_in(
                            (DocumentStatus.PENDING_DELETE.value, DocumentStatus.DELETED.value)
                        ),
                    )
                ),
            )
            .values(updated_at=now)
        )
        if _rowcount(result) != 1:
            self._raise_fence_failure(fence)
        self._session.flush()

    def _raise_fence_failure(self, fence: JobFence) -> None:
        """中文：区分取消、文档代次失效和普通租约丢失，驱动正确的 Worker 收口。

        English: Distinguish cancellation, lifecycle staleness, and ordinary lease loss.
        """

        job = self._session.scalar(
            select(IngestionJobRow).where(
                IngestionJobRow.tenant_id == fence.tenant_id,
                IngestionJobRow.id == fence.job_id,
            )
        )
        if job is not None and job.cancel_requested_at is not None:
            raise JobCancelledError(
                error_detail(
                    "INGESTION_CANCELLED",
                    ErrorCategory.CONFLICT,
                    "The ingestion job was cancelled before publication.",
                    job_id=fence.job_id,
                )
            )
        document = self._session.scalar(
            select(DocumentRow).where(
                DocumentRow.tenant_id == fence.tenant_id,
                DocumentRow.id == fence.document_id,
            )
        )
        if (
            document is None
            or document.lifecycle_generation != fence.document_generation
            or document.status
            in {DocumentStatus.PENDING_DELETE.value, DocumentStatus.DELETED.value}
        ):
            raise LifecycleFenceError(
                error_detail(
                    "DOCUMENT_LIFECYCLE_FENCE_REJECTED",
                    ErrorCategory.CONFLICT,
                    "The document lifecycle invalidated this ingestion attempt.",
                    document_id=fence.document_id,
                )
            )
        raise LeaseLostError(
            error_detail(
                "INGESTION_LEASE_LOST",
                ErrorCategory.CONFLICT,
                "The ingestion worker no longer owns this job attempt.",
                job_id=fence.job_id,
            )
        )

    def replace_version_chunks_fenced(
        self,
        fence: JobFence,
        document_version_id: str,
        chunks: Sequence[Chunk],
        now: datetime,
    ) -> None:
        """中文：验证 fencing 后原子替换候选文档版本的全部 Chunk。

        English: Verify the fence and atomically replace all chunks for a candidate version.
        """

        self.assert_job_fence(fence, now)
        self.replace_version_chunks(fence.tenant_id, document_version_id, chunks)

    def update_version_quality_metrics_fenced(
        self,
        fence: JobFence,
        document_version_id: str,
        metrics: dict[str, object],
        warnings: tuple[str, ...],
        now: datetime,
    ) -> None:
        """中文：验证 fencing 后写入候选版本的质量指标与警告。

        English: Verify the fence before storing quality metrics and warnings for a candidate.
        """

        self.assert_job_fence(fence, now)
        self.update_version_quality_metrics(
            fence.tenant_id,
            document_version_id,
            metrics,
            warnings,
        )

    def mark_job_succeeded(self, fence: JobFence, now: datetime) -> None:
        """中文：该函数或方法负责“标记任务成功的”相关处理。

        English: Mark a job as succeeded and release its worker lease.
        """

        self._update_job_terminal(
            fence=fence,
            now=now,
            status=JobStatus.SUCCEEDED,
            error_code=None,
            error_message=None,
        )

    def mark_job_failed(
        self,
        fence: JobFence,
        now: datetime,
        error_code: str,
        error_message: str,
    ) -> None:
        """中文：该函数或方法负责“标记任务失败的”相关处理。

        English: Mark a job as failed and retain only safe diagnostics.
        """

        self._update_job_terminal(
            fence=fence,
            now=now,
            status=JobStatus.FAILED,
            error_code=error_code,
            error_message=error_message,
        )

    def mark_job_cancelled(self, fence: JobFence, now: datetime, reason: str) -> None:
        """中文：把当前运行代次收口为 CANCELLED，且不覆盖文档删除状态。

        English: Terminally cancel the current attempt without overwriting document deletion.
        """

        result = self._session.execute(
            update(IngestionJobRow)
            .where(
                IngestionJobRow.tenant_id == fence.tenant_id,
                IngestionJobRow.id == fence.job_id,
                IngestionJobRow.status == JobStatus.RUNNING.value,
                IngestionJobRow.lease_owner == fence.lease_owner,
                IngestionJobRow.attempt_count == fence.attempt_count,
            )
            .values(
                status=JobStatus.CANCELLED.value,
                lease_owner=None,
                lease_expires_at=None,
                cancel_requested_at=now,
                cancel_reason=reason,
                updated_at=now,
            )
        )
        if _rowcount(result) != 1:
            self._raise_fence_failure(fence)
        self._session.flush()

    def mark_job_attention_required(
        self,
        fence: JobFence,
        now: datetime,
        status: JobStatus,
        error_code: str,
        error_message: str,
    ) -> None:
        """中文：将任务置为 OCR、复核或不支持等可解释终态。

        English: Mark a job with an explainable OCR, review, or unsupported terminal state.
        """

        if status not in {
            JobStatus.NEEDS_OCR,
            JobStatus.NEEDS_REVIEW,
            JobStatus.UNSUPPORTED,
        }:
            raise ValueError("attention status must be needs_ocr, needs_review, or unsupported")
        self._update_job_terminal(
            fence=fence,
            now=now,
            status=status,
            error_code=error_code,
            error_message=error_message,
        )

    def _update_job_terminal(
        self,
        fence: JobFence,
        now: datetime,
        status: JobStatus,
        error_code: str | None,
        error_message: str | None,
    ) -> None:
        """中文：该内部函数负责“更新任务终态”相关处理。

        English: Apply one terminal job transition and release its lease.
        """

        result = self._session.execute(
            update(IngestionJobRow)
            .where(
                IngestionJobRow.tenant_id == fence.tenant_id,
                IngestionJobRow.id == fence.job_id,
                IngestionJobRow.status == JobStatus.RUNNING.value,
                IngestionJobRow.lease_owner == fence.lease_owner,
                IngestionJobRow.attempt_count == fence.attempt_count,
                IngestionJobRow.lease_expires_at.is_not(None),
                IngestionJobRow.lease_expires_at > now,
            )
            .values(
                status=status.value,
                lease_owner=None,
                lease_expires_at=None,
                error_code=error_code,
                error_message=error_message,
                updated_at=now,
            )
        )
        if _rowcount(result) != 1:
            raise LeaseLostError(
                error_detail(
                    "INGESTION_LEASE_LOST",
                    ErrorCategory.CONFLICT,
                    "The ingestion worker no longer owns this job attempt.",
                    job_id=fence.job_id,
                )
            )
        self._session.flush()

    def add_index(self, index: IndexVersion) -> None:
        """中文：该函数或方法负责“新增索引”相关处理。

        English: Persist a staged or ready immutable index version.
        """

        self._session.add(
            IndexVersionRow(
                id=index.id,
                tenant_id=index.tenant_id,
                status=index.status.value,
                storage_key=index.storage_key,
                chunk_count=index.chunk_count,
                config_fingerprint=index.config_fingerprint,
                created_at=index.created_at,
                activated_at=index.activated_at,
                error_code=index.error_code,
                error_message=index.error_message,
                completed_at=index.completed_at,
            )
        )
        self._session.flush()

    def get_active_index(self, tenant_id: str) -> IndexVersion | None:
        """中文：该函数或方法负责“获取活动索引”相关处理。

        English: Return the single active index snapshot for a tenant.
        """

        row = self._session.scalar(
            select(IndexVersionRow).where(
                IndexVersionRow.tenant_id == tenant_id,
                IndexVersionRow.status == IndexStatus.ACTIVE.value,
            )
        )
        return _index_from_row(row) if row is not None else None

    def set_index_status(
        self,
        tenant_id: str,
        index_version_id: str,
        status: IndexStatus,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """中文：该函数或方法负责“设置索引状态”相关处理。

        English: Update one tenant-owned index publication state.
        """

        row = self._session.scalar(
            select(IndexVersionRow)
            .where(
                IndexVersionRow.tenant_id == tenant_id,
                IndexVersionRow.id == index_version_id,
            )
            .with_for_update()
        )
        if row is None:
            raise ValueError("the tenant-owned index version does not exist")
        current_status = IndexStatus(row.status)
        ensure_transition(current_status, status, INDEX_TRANSITIONS)
        result = self._session.execute(
            update(IndexVersionRow)
            .where(
                IndexVersionRow.tenant_id == tenant_id,
                IndexVersionRow.id == index_version_id,
                IndexVersionRow.status == current_status.value,
            )
            .values(
                status=status.value,
                error_code=error_code,
                error_message=error_message,
                completed_at=(
                    utc_now()
                    if status
                    in {
                        IndexStatus.ACTIVE,
                        IndexStatus.FAILED,
                        IndexStatus.CANCELLED,
                        IndexStatus.PURGED,
                    }
                    else None
                ),
            )
        )
        if _rowcount(result) != 1:
            raise ValueError("the index state changed before this transition committed")
        self._session.flush()

    def activate_index(
        self,
        tenant_id: str,
        index_version_id: str,
        expected_active_index_id: str | None | object = _UNSET_ACTIVE_INDEX,
    ) -> str | None:
        """中文：该函数或方法负责“激活索引”相关处理。

        English: Retire the prior snapshot and activate a ready snapshot atomically.
        """

        # 中文：关键的无变化 UPDATE 在 PostgreSQL 上锁定租户行，在 SQLite
        # 上提前取得写锁，从而把同一租户的激活事务串行化。
        # English: A no-op UPDATE locks the tenant row on PostgreSQL and acquires SQLite's
        # write lock early, serializing activation transactions for the same tenant.
        tenant_lock = self._session.execute(
            update(TenantRow)
            .where(TenantRow.id == tenant_id)
            .values(name=TenantRow.name)
        )
        if _rowcount(tenant_lock) != 1:
            raise ValueError("the index tenant does not exist")
        # 中文：关键变量 `current` 在锁定后读取，用于执行真实的乐观并发校验。
        # English: Key variable `current` is read after locking and drives the real
        # optimistic-concurrency comparison.
        current = self._session.scalar(
            select(IndexVersionRow).where(
                IndexVersionRow.tenant_id == tenant_id,
                IndexVersionRow.status == IndexStatus.ACTIVE.value,
            )
        )
        current_id = current.id if current is not None else None
        if (
            expected_active_index_id is not _UNSET_ACTIVE_INDEX
            and current_id != expected_active_index_id
        ):
            raise StaleIndexBuildPlanError(
                error_detail(
                    "STALE_INDEX_BUILD_PLAN",
                    ErrorCategory.CONFLICT,
                    "The active index changed while the new snapshot was being built.",
                    expected_index_id=str(expected_active_index_id),
                    current_index_id=str(current_id),
                )
            )
        # 中文：变量 `target` 用于保存“`target`”相关数据；其精确定义与约束见下方英文说明。
        # English: Target lock prevents concurrent publication races where supported.
        target = self._session.scalar(
            select(IndexVersionRow)
            .where(
                IndexVersionRow.tenant_id == tenant_id,
                IndexVersionRow.id == index_version_id,
                IndexVersionRow.status == IndexStatus.READY.value,
            )
            .with_for_update()
        )
        if target is None:
            raise ValueError("only a tenant-owned READY index can be activated")
        if current is not None:
            current.status = IndexStatus.RETIRED.value
        target.status = IndexStatus.ACTIVE.value
        target.activated_at = utc_now()
        target.completed_at = target.activated_at
        self._session.flush()
        return current_id

    def list_indexes(self, tenant_id: str) -> Sequence[IndexVersion]:
        """中文：该函数或方法负责“列出索引”相关处理。

        English: Return tenant index versions from newest to oldest.
        """

        rows = self._session.scalars(
            select(IndexVersionRow)
            .where(IndexVersionRow.tenant_id == tenant_id)
            .order_by(IndexVersionRow.created_at.desc(), IndexVersionRow.id.desc())
        ).all()
        return tuple(_index_from_row(row) for row in rows)

    def add_trace(self, trace: TraceRecord) -> None:
        """中文：该函数或方法负责“新增追踪”相关处理。

        English: Persist one redacted trace summary.
        """

        self._session.add(
            TraceRow(
                id=trace.id,
                tenant_id=trace.tenant_id,
                user_id=trace.user_id,
                operation=trace.operation,
                status=trace.status,
                index_version_id=trace.index_version_id,
                attributes=trace.attributes,
                created_at=trace.created_at,
                completed_at=trace.completed_at,
            )
        )
        self._session.flush()

    def get_trace(self, tenant_id: str, trace_id: str) -> TraceRecord | None:
        """中文：该函数或方法负责“获取追踪”相关处理。

        English: Return a redacted trace only inside the requested tenant.
        """

        row = self._session.scalar(
            select(TraceRow).where(
                TraceRow.tenant_id == tenant_id,
                TraceRow.id == trace_id,
            )
        )
        return _trace_from_row(row) if row is not None else None

    def finish_trace(
        self,
        tenant_id: str,
        trace_id: str,
        status: str,
        attributes: dict[str, object],
    ) -> None:
        """中文：持久化追踪终态并合并安全聚合指标。

        English: Persist a terminal trace status and merge safe aggregate metrics.
        """

        row = self._session.scalar(
            select(TraceRow).where(
                TraceRow.tenant_id == tenant_id,
                TraceRow.id == trace_id,
            )
        )
        if row is None:
            return
        row.status = status[:32]
        row.attributes = {**dict(row.attributes or {}), **attributes}
        row.completed_at = utc_now()
        self._session.flush()


def _source_from_row(row: SourceRow) -> Source:
    """中文：该内部函数负责“资料源从数据行”相关处理。

    English: Map a persistence source row to an immutable domain entity.
    """

    return Source(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        description=row.description,
        content_profile=ContentProfile(row.content_profile),
        chunk_strategy_override=row.chunk_strategy_override,
        visibility=SourceVisibility(row.visibility),
        allowed_group_ids=frozenset(row.allowed_group_ids),
        is_active=row.is_active,
        created_at=row.created_at,
    )


def _document_from_row(row: DocumentRow) -> Document:
    """中文：该内部函数负责“文档从数据行”相关处理。

    English: Map a persistence document row to an immutable domain entity.
    """

    return Document(
        id=row.id,
        tenant_id=row.tenant_id,
        source_id=row.source_id,
        title=row.title,
        status=DocumentStatus(row.status),
        active_version_id=row.active_version_id,
        lifecycle_generation=row.lifecycle_generation,
        delete_requested_at=row.delete_requested_at,
        deleted_at=row.deleted_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _version_from_row(row: DocumentVersionRow) -> DocumentVersion:
    """中文：该内部函数负责“版本从数据行”相关处理。

    English: Map a persistence version row to an immutable domain entity.
    """

    # 中文：历史数据的空快照使用兼容默认值，后续重处理将生成完整新快照。
    # English: Empty historical snapshots use safe defaults; reprocessing creates full data.
    snapshot = _json_mapping(row.ingestion_snapshot)
    raw_profile = str(snapshot.get("content_profile", ContentProfile.GENERAL_PROSE.value))
    return DocumentVersion(
        id=row.id,
        tenant_id=row.tenant_id,
        document_id=row.document_id,
        source_id=row.source_id,
        version_number=row.version_number,
        original_filename=row.original_filename,
        media_type=row.media_type,
        content_hash=row.content_hash,
        storage_key=row.storage_key,
        size_bytes=row.size_bytes,
        content_profile=ContentProfile(raw_profile),
        chunk_strategy_id=str(snapshot.get("chunk_strategy_id", "general-prose")),
        chunk_strategy_version=str(
            snapshot.get("chunk_strategy_version", "general-prose-v1")
        ),
        chunk_parameters=_json_mapping(snapshot.get("chunk_parameters")),
        embedding_fingerprint=str(snapshot.get("embedding_fingerprint", "")),
        boundary_model_fingerprint=(
            str(snapshot["boundary_model_fingerprint"])
            if snapshot.get("boundary_model_fingerprint")
            else None
        ),
        profile_confidence=_safe_float(snapshot.get("profile_confidence"), 1.0),
        tokenizer_id=str(snapshot.get("tokenizer_id", "unicode-codepoint-v1")),
        extraction_pipeline_version=str(
            snapshot.get("extraction_pipeline_version", "extraction-v4")
        ),
        quality_metrics=_json_mapping(snapshot.get("quality_metrics")),
        created_at=row.created_at,
    )


def _chunk_to_row(chunk: Chunk) -> ChunkRow:
    """中文：该内部函数负责“文本块到数据行”相关处理。

    English: Map an immutable chunk entity to its persistence row.
    """

    # 中文：新增层级与边界字段编码进 JSON，保持现有数据库表向后兼容。
    # English: New hierarchy and boundary fields are encoded in JSON for schema compatibility.
    persisted_metadata = {
        **chunk.metadata,
        "retrieval_text": chunk.retrieval_text,
        "parent_chunk_id": chunk.parent_chunk_id,
        "chunk_level": chunk.chunk_level,
        "unit_type": chunk.unit_type,
        "section_number": chunk.section_number,
        "source_start_offset": chunk.source_start_offset,
        "source_end_offset": chunk.source_end_offset,
        "boundary_method": chunk.boundary_method,
        "boundary_confidence": chunk.boundary_confidence,
    }
    return ChunkRow(
        id=chunk.id,
        tenant_id=chunk.tenant_id,
        source_id=chunk.source_id,
        document_id=chunk.document_id,
        document_version_id=chunk.document_version_id,
        ordinal=chunk.ordinal,
        text=chunk.text,
        token_count=chunk.token_count,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        heading_path=list(chunk.heading_path),
        previous_chunk_id=chunk.previous_chunk_id,
        next_chunk_id=chunk.next_chunk_id,
        boundary_reason=chunk.boundary_reason,
        chunker_version=chunk.chunker_version,
        content_hash=chunk.content_hash,
        extra_metadata=persisted_metadata,
    )


def _chunk_from_row(row: ChunkRow) -> Chunk:
    """中文：该内部函数负责“文本块从数据行”相关处理。

    English: Map a persistence chunk row to an immutable domain entity.
    """

    # 中文：V4 之前的数据缺少新增键时使用安全默认值，无需破坏性迁移。
    # English: Safe defaults keep pre-V4 rows readable without a destructive migration.
    metadata = _json_mapping(row.extra_metadata)
    return Chunk(
        id=row.id,
        tenant_id=row.tenant_id,
        source_id=row.source_id,
        document_id=row.document_id,
        document_version_id=row.document_version_id,
        ordinal=row.ordinal,
        text=row.text,
        token_count=row.token_count,
        page_start=row.page_start,
        page_end=row.page_end,
        heading_path=tuple(row.heading_path),
        previous_chunk_id=row.previous_chunk_id,
        next_chunk_id=row.next_chunk_id,
        boundary_reason=row.boundary_reason,
        chunker_version=row.chunker_version,
        content_hash=row.content_hash,
        retrieval_text=str(metadata.get("retrieval_text", "")),
        parent_chunk_id=(
            str(metadata["parent_chunk_id"]) if metadata.get("parent_chunk_id") else None
        ),
        chunk_level=str(metadata.get("chunk_level", "leaf")),
        unit_type=str(metadata.get("unit_type", "prose")),
        section_number=(
            str(metadata["section_number"]) if metadata.get("section_number") else None
        ),
        source_start_offset=_safe_int(metadata.get("source_start_offset"), 0),
        source_end_offset=_safe_int(metadata.get("source_end_offset"), 0),
        boundary_method=str(metadata.get("boundary_method", row.boundary_reason)),
        boundary_confidence=_safe_float(metadata.get("boundary_confidence"), 1.0),
        metadata=metadata,
    )


def _json_mapping(value: object) -> dict[str, object]:
    """中文：把不可信 JSON 值安全收窄为字符串键映射。

    English: Safely narrow an untrusted JSON value to a string-keyed mapping.
    """

    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _safe_int(value: object, default: int) -> int:
    """中文：解析持久化整数，并在旧数据类型异常时返回默认值。

    English: Parse a persisted integer and default malformed historical values.
    """

    if isinstance(value, (int, float, str)):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _safe_float(value: object, default: float) -> float:
    """中文：解析持久化浮点数，并在旧数据类型异常时返回默认值。

    English: Parse a persisted float and default malformed historical values.
    """

    if isinstance(value, (int, float, str)):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _job_from_row(row: IngestionJobRow) -> IngestionJob:
    """中文：该内部函数负责“任务从数据行”相关处理。

    English: Map a persistence job row to an immutable domain entity.
    """

    return IngestionJob(
        id=row.id,
        tenant_id=row.tenant_id,
        document_id=row.document_id,
        document_version_id=row.document_version_id,
        document_generation_snapshot=row.document_generation_snapshot,
        status=JobStatus(row.status),
        attempt_count=row.attempt_count,
        lease_owner=row.lease_owner,
        lease_expires_at=row.lease_expires_at,
        error_code=row.error_code,
        error_message=row.error_message,
        cancel_requested_at=row.cancel_requested_at,
        cancel_reason=row.cancel_reason,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _index_from_row(row: IndexVersionRow) -> IndexVersion:
    """中文：该内部函数负责“索引从数据行”相关处理。

    English: Map a persistence index row to an immutable domain entity.
    """

    return IndexVersion(
        id=row.id,
        tenant_id=row.tenant_id,
        status=IndexStatus(row.status),
        storage_key=row.storage_key,
        chunk_count=row.chunk_count,
        config_fingerprint=row.config_fingerprint,
        created_at=row.created_at,
        activated_at=row.activated_at,
        error_code=row.error_code,
        error_message=row.error_message,
        completed_at=row.completed_at,
    )


def _trace_from_row(row: TraceRow) -> TraceRecord:
    """中文：该内部函数负责“追踪从数据行”相关处理。

    English: Map a persistence trace row to an immutable domain entity.
    """

    return TraceRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        user_id=row.user_id,
        operation=row.operation,
        status=row.status,
        index_version_id=row.index_version_id,
        attributes=row.attributes,
        created_at=row.created_at,
        completed_at=row.completed_at,
    )
