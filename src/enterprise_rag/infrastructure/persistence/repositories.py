"""中文：本模块负责实现“仓储”相关功能。

English: Implement tenant-scoped domain repositories with one caller-owned SQLAlchemy session.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from enterprise_rag.core.enums import (
    ContentProfile,
    DocumentStatus,
    ErrorCategory,
    IndexStatus,
    JobStatus,
    JobType,
    LeaseCheckResult,
    QualityDecision,
    RevocationScopeType,
    SnapshotStatus,
    SourceVisibility,
    StructureType,
)
from enterprise_rag.core.exceptions import (
    DocumentGenerationStaleError,
    JobCancelledError,
    LeaseExpiredError,
    LeaseLostError,
    LeaseOwnershipLostError,
    LifecycleFenceError,
    StaleIndexBuildPlanError,
    error_detail,
)
from enterprise_rag.core.ids import new_id
from enterprise_rag.core.state_machine import (
    DOCUMENT_TRANSITIONS,
    INDEX_TRANSITIONS,
    ensure_transition,
)
from enterprise_rag.domain.locators import (
    DisplayLocator,
    LocatorBundle,
    LocatorMappingQuality,
    NormalizedRange,
    OCRBox,
    OriginalLocator,
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
from enterprise_rag.domain.quality import (
    IngestionQualityReport,
    QualityFinding,
)
from enterprise_rag.domain.snapshots import KnowledgeSnapshot, RevocationRecord
from enterprise_rag.infrastructure.persistence.orm_models import (
    ChunkRow,
    DocumentRow,
    DocumentVersionRow,
    IndexVersionRow,
    IngestionJobRow,
    QualityReportRow,
    QuerySnapshotDocumentVersionRow,
    QuerySnapshotRow,
    RevocationRow,
    SourceRow,
    TenantKnowledgeStateRow,
    TenantRow,
    TraceRow,
)

# 中文：哨兵区分“未启用乐观校验”和“期望当前没有活动索引”。
# English: Sentinel distinguishes disabled optimistic checks from expecting no active index.
_UNSET_ACTIVE_INDEX = object()


def _job_document_state_predicate(fence: JobFence) -> ColumnElement[bool]:
    """中文：删除任务必须处于 PENDING_DELETE，其他任务则必须排除删除态。

    English: Require PENDING_DELETE for deletion jobs and non-deleting state for all others.
    """

    base_document = (
        DocumentRow.tenant_id == fence.tenant_id,
        DocumentRow.id == fence.document_id,
        DocumentRow.lifecycle_generation == fence.document_generation,
    )
    deleting_document_ids = select(DocumentRow.id).where(
        *base_document,
        DocumentRow.status == DocumentStatus.PENDING_DELETE.value,
    )
    ordinary_document_ids = select(DocumentRow.id).where(
        *base_document,
        DocumentRow.status.not_in(
            (DocumentStatus.PENDING_DELETE.value, DocumentStatus.DELETED.value)
        ),
    )
    return or_(
        (IngestionJobRow.job_type == JobType.DELETION.value)
        & IngestionJobRow.document_id.in_(deleting_document_ids),
        (IngestionJobRow.job_type != JobType.DELETION.value)
        & IngestionJobRow.document_id.in_(ordinary_document_ids),
    )


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
                next_version_number=document.next_version_number,
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

    def list_document_versions(
        self,
        tenant_id: str,
        document_id: str,
    ) -> Sequence[DocumentVersion]:
        """中文：返回逻辑文档的全部不可变版本，供删除和溯源使用。

        English: Return every immutable version of a logical document for deletion and provenance.
        """

        rows = self._session.scalars(
            select(DocumentVersionRow)
            .where(
                DocumentVersionRow.tenant_id == tenant_id,
                DocumentVersionRow.document_id == document_id,
            )
            .order_by(DocumentVersionRow.version_number, DocumentVersionRow.id)
        ).all()
        return tuple(_version_from_row(row) for row in rows)

    def next_version_number(self, tenant_id: str, document_id: str) -> int:
        """中文：在单条数据库语句中原子分配并递增文档版本号。

        English: Atomically allocate and increment a document version number in one statement.
        """

        # 中文：关键变量 `new_counter` 是原子 UPDATE 后的下一次计数，当前分配值为其减一。
        # English: Key variable `new_counter` is the post-update counter; this allocation is one
        # less. COALESCE only protects incompletely migrated rows and never queries max(version).
        new_counter = self._session.scalar(
            update(DocumentRow)
            .where(
                DocumentRow.tenant_id == tenant_id,
                DocumentRow.id == document_id,
                DocumentRow.status.not_in(
                    (DocumentStatus.PENDING_DELETE.value, DocumentStatus.DELETED.value)
                ),
            )
            .values(next_version_number=func.coalesce(DocumentRow.next_version_number, 2) + 1)
            .returning(DocumentRow.next_version_number)
        )
        if new_counter is None:
            raise LifecycleFenceError(
                error_detail(
                    "DOCUMENT_VERSION_ALLOCATION_REJECTED",
                    ErrorCategory.CONFLICT,
                    "The document cannot allocate a new version in its current lifecycle.",
                    document_id=document_id,
                )
            )
        self._session.flush()
        return int(new_counter) - 1

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

    def add_quality_report(self, report: IngestionQualityReport) -> None:
        """中文：为不可变文档版本写入一份独立且幂等的质量报告。

        English: Persist one independent, idempotent quality report for an immutable version.
        """

        version_row = self._session.scalar(
            select(DocumentVersionRow).where(
                DocumentVersionRow.tenant_id == report.tenant_id,
                DocumentVersionRow.id == report.document_version_id,
                DocumentVersionRow.document_id == report.document_id,
            )
        )
        if version_row is None:
            raise ValueError("quality report document version does not exist")
        existing = self._session.scalar(
            select(QualityReportRow).where(
                QualityReportRow.document_version_id == report.document_version_id
            )
        )
        if existing is not None:
            if existing.id != report.id:
                raise ValueError("document version already has a different quality report")
            version_row.quality_report_id = existing.id
            self._session.flush()
            return
        self._session.add(
            QualityReportRow(
                id=report.id,
                tenant_id=report.tenant_id,
                document_id=report.document_id,
                document_version_id=report.document_version_id,
                decision=report.decision.value,
                metrics_json=dict(report.metrics),
                findings_json=[
                    {
                        "code": finding.code,
                        "severity": finding.severity,
                        "message": finding.message,
                    }
                    for finding in report.findings
                ],
                degradation_codes=list(report.degradation_codes),
                validator_version=report.validator_version,
                created_at=report.created_at,
            )
        )
        version_row.quality_report_id = report.id
        self._session.flush()

    def get_quality_report(
        self,
        tenant_id: str,
        document_version_id: str,
    ) -> IngestionQualityReport | None:
        """中文：按租户和不可变版本读取独立质量报告。

        English: Read an independent quality report by tenant and immutable version.
        """

        row = self._session.scalar(
            select(QualityReportRow).where(
                QualityReportRow.tenant_id == tenant_id,
                QualityReportRow.document_version_id == document_version_id,
            )
        )
        if row is None:
            return None
        findings: list[QualityFinding] = []
        for raw in row.findings_json:
            if not isinstance(raw, dict):
                continue
            code = raw.get("code")
            severity = raw.get("severity")
            message = raw.get("message")
            if all(isinstance(value, str) for value in (code, severity, message)):
                findings.append(
                    QualityFinding(
                        code=str(code),
                        severity=str(severity),
                        message=str(message),
                    )
                )
        return IngestionQualityReport(
            id=row.id,
            tenant_id=row.tenant_id,
            document_id=row.document_id,
            document_version_id=row.document_version_id,
            decision=QualityDecision(row.decision),
            validator_version=row.validator_version,
            created_at=row.created_at,
            metrics=dict(row.metrics_json),
            findings=tuple(findings),
            degradation_codes=tuple(row.degradation_codes),
        )

    def list_active_chunks(self, tenant_id: str) -> Sequence[Chunk]:
        """中文：该函数或方法负责“列出活动文本块”相关处理。

        English: Return chunks belonging only to ready documents' active versions.
        """

        rows = self._session.scalars(
            select(ChunkRow)
            .join(DocumentRow, DocumentRow.active_version_id == ChunkRow.document_version_id)
            .join(
                SourceRow,
                (SourceRow.id == ChunkRow.source_id) & (SourceRow.tenant_id == ChunkRow.tenant_id),
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
                (SourceRow.id == ChunkRow.source_id) & (SourceRow.tenant_id == ChunkRow.tenant_id),
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

    def get_snapshot_chunks(
        self,
        tenant_id: str,
        chunk_ids: Sequence[str],
        document_version_ids: frozenset[str],
    ) -> Sequence[Chunk]:
        """中文：从请求固定版本集读取 Chunk，同时立即应用 Source 撤权和文档删除。

        English: Load chunks from pinned versions while immediately enforcing source revocation
        and document deletion.
        """

        if not chunk_ids or not document_version_ids:
            return ()
        rows = self._session.scalars(
            select(ChunkRow)
            .join(
                DocumentRow,
                (DocumentRow.id == ChunkRow.document_id)
                & (DocumentRow.tenant_id == ChunkRow.tenant_id),
            )
            .join(
                SourceRow,
                (SourceRow.id == ChunkRow.source_id) & (SourceRow.tenant_id == ChunkRow.tenant_id),
            )
            .where(
                ChunkRow.tenant_id == tenant_id,
                ChunkRow.id.in_(chunk_ids),
                ChunkRow.document_version_id.in_(document_version_ids),
                DocumentRow.status.not_in(
                    (DocumentStatus.PENDING_DELETE.value, DocumentStatus.DELETED.value)
                ),
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
                idempotency_key=job.idempotency_key,
                job_type=job.job_type.value,
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

    def get_job_by_idempotency(
        self,
        tenant_id: str,
        job_type: JobType,
        idempotency_key: str | None,
    ) -> IngestionJob | None:
        """中文：按租户、任务类型和非空幂等键查找原任务。

        English: Find the original job by tenant, job type, and a nonempty idempotency key.
        """

        if not idempotency_key:
            return None
        row = self._session.scalar(
            select(IngestionJobRow).where(
                IngestionJobRow.tenant_id == tenant_id,
                IngestionJobRow.job_type == job_type.value,
                IngestionJobRow.idempotency_key == idempotency_key,
            )
        )
        return _job_from_row(row) if row is not None else None

    def get_latest_document_job(
        self,
        tenant_id: str,
        document_id: str,
        job_type: JobType,
    ) -> IngestionJob | None:
        """中文：按文档和任务类型查找最新任务，用于无幂等键的重复删除请求。

        English: Find the latest document job by type for repeated deletion without an idempotency
        key.
        """

        row = self._session.scalar(
            select(IngestionJobRow)
            .where(
                IngestionJobRow.tenant_id == tenant_id,
                IngestionJobRow.document_id == document_id,
                IngestionJobRow.job_type == job_type.value,
            )
            .order_by(IngestionJobRow.created_at.desc(), IngestionJobRow.id.desc())
            .limit(1)
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
                ),
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

        return self.renew_job_lease_result(fence, now, lease_until) is LeaseCheckResult.VALID

    def renew_job_lease_result(
        self,
        fence: JobFence,
        now: datetime,
        lease_until: datetime,
    ) -> LeaseCheckResult:
        """中文：续租并返回取消、失租、过期或代次失效的精确结果。

        English: Renew a lease and return the exact cancellation, ownership, expiration, or
        generation outcome.
        """

        if lease_until <= now:
            raise ValueError("renewed lease must expire after the renewal time")
        initial_result = self.inspect_job_fence(fence, now)
        if initial_result is not LeaseCheckResult.VALID:
            return initial_result
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
                _job_document_state_predicate(fence),
            )
            .values(lease_expires_at=lease_until, updated_at=now)
        )
        self._session.flush()
        if _rowcount(result) == 1:
            return LeaseCheckResult.VALID
        # 中文：检查与 CAS 更新之间可能发生状态变化，必须按最新持久状态重新分类。
        # English: State can change between inspection and CAS; classify the latest durable row.
        return self.inspect_job_fence(fence, now)

    def inspect_job_fence(self, fence: JobFence, now: datetime) -> LeaseCheckResult:
        """中文：只读判定一个任务 fencing token 当前为何有效或失效。

        English: Read and classify why a job fencing token is currently valid or invalid.

        中文：所有权优先于取消判断，确保旧 Worker 永远不能替新租约写 CANCELLED。
        English: Ownership precedes cancellation so an old worker can never cancel a new lease.
        """

        job = self._session.scalar(
            select(IngestionJobRow).where(
                IngestionJobRow.tenant_id == fence.tenant_id,
                IngestionJobRow.id == fence.job_id,
            )
        )
        if (
            job is None
            or job.status != JobStatus.RUNNING.value
            or job.lease_owner != fence.lease_owner
            or job.attempt_count != fence.attempt_count
        ):
            return LeaseCheckResult.LEASE_OWNERSHIP_LOST
        if job.cancel_requested_at is not None:
            return LeaseCheckResult.CANCEL_REQUESTED
        lease_expires_at = job.lease_expires_at
        if lease_expires_at is not None and lease_expires_at.tzinfo is None:
            # 中文：SQLite 会丢失时区信息；领域比较统一按 UTC 恢复，不改变持久值。
            # English: SQLite drops timezone metadata; restore UTC for domain comparison only.
            lease_expires_at = lease_expires_at.replace(tzinfo=UTC)
        if lease_expires_at is None or lease_expires_at <= now:
            return LeaseCheckResult.LEASE_EXPIRED
        document = self._session.scalar(
            select(DocumentRow).where(
                DocumentRow.tenant_id == fence.tenant_id,
                DocumentRow.id == fence.document_id,
            )
        )
        generation_mismatch = (
            document is None
            or job.document_id != fence.document_id
            or job.document_generation_snapshot != fence.document_generation
            or document.lifecycle_generation != fence.document_generation
        )
        deletion_state_invalid = job.job_type == JobType.DELETION.value and (
            document is None or document.status != DocumentStatus.PENDING_DELETE.value
        )
        ordinary_state_invalid = job.job_type != JobType.DELETION.value and (
            document is None
            or document.status
            in {DocumentStatus.PENDING_DELETE.value, DocumentStatus.DELETED.value}
        )
        if generation_mismatch or deletion_state_invalid or ordinary_state_invalid:
            return LeaseCheckResult.DOCUMENT_GENERATION_STALE
        return LeaseCheckResult.VALID

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
                _job_document_state_predicate(fence),
            )
            .values(updated_at=now)
        )
        if _rowcount(result) != 1:
            self._raise_for_lease_result(self.inspect_job_fence(fence, now), fence)
        self._session.flush()

    def _raise_for_lease_result(
        self,
        result: LeaseCheckResult,
        fence: JobFence,
    ) -> None:
        """中文：把结构化租约结果转换为具有稳定错误码的领域异常。

        English: Convert a structured lease result into a domain exception with a stable code.
        """

        if result is LeaseCheckResult.CANCEL_REQUESTED:
            raise JobCancelledError(
                error_detail(
                    "INGESTION_CANCELLED",
                    ErrorCategory.CONFLICT,
                    "The ingestion job was cancelled before publication.",
                    job_id=fence.job_id,
                )
            )
        if result is LeaseCheckResult.DOCUMENT_GENERATION_STALE:
            raise DocumentGenerationStaleError(
                error_detail(
                    "DOCUMENT_LIFECYCLE_FENCE_REJECTED",
                    ErrorCategory.CONFLICT,
                    "The document lifecycle invalidated this ingestion attempt.",
                    document_id=fence.document_id,
                )
            )
        if result is LeaseCheckResult.LEASE_EXPIRED:
            raise LeaseExpiredError(
                error_detail(
                    "INGESTION_LEASE_EXPIRED",
                    ErrorCategory.CONFLICT,
                    "The ingestion worker lease expired before this checkpoint.",
                    job_id=fence.job_id,
                )
            )
        raise LeaseOwnershipLostError(
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

    def add_quality_report_fenced(
        self,
        fence: JobFence,
        report: IngestionQualityReport,
        now: datetime,
    ) -> None:
        """中文：验证租约和 generation 后写入独立质量报告。

        English: Persist an independent quality report after validating lease and generation.
        """

        self.assert_job_fence(fence, now)
        if report.tenant_id != fence.tenant_id or report.document_id != fence.document_id:
            raise ValueError("quality report scope does not match the active job fence")
        self.add_quality_report(report)

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
            lease_result = self.inspect_job_fence(fence, now)
            # 中文：当前代次可在已请求取消时写入 CANCELLED；其他失效原因禁止覆盖。
            # English: The current generation may close a requested cancellation; other stale
            # workers cannot overwrite the durable state.
            if lease_result is not LeaseCheckResult.CANCEL_REQUESTED:
                self._raise_for_lease_result(lease_result, fence)
        self._session.flush()

    def mark_job_stale(self, fence: JobFence, now: datetime, reason: str) -> None:
        """中文：仅由仍匹配的任务代次将 generation 失效收口为 STALE。

        English: Close a generation-invalidated job as STALE only for the matching attempt.
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
                status=JobStatus.STALE.value,
                lease_owner=None,
                lease_expires_at=None,
                error_code="DOCUMENT_GENERATION_STALE",
                error_message=reason,
                updated_at=now,
            )
        )
        if _rowcount(result) != 1:
            self._raise_for_lease_result(self.inspect_job_fence(fence, now), fence)
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
            update(TenantRow).where(TenantRow.id == tenant_id).values(name=TenantRow.name)
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

    def current_revocation_epoch(self, tenant_id: str) -> int:
        """中文：返回租户知识撤销序号，首次读取时建立零值状态。

        English: Return the tenant revocation epoch and initialize it to zero on first use.
        """

        row = self._session.get(TenantKnowledgeStateRow, tenant_id)
        if row is None:
            row = TenantKnowledgeStateRow(tenant_id=tenant_id, revocation_epoch=0)
            self._session.add(row)
            self._session.flush()
        return row.revocation_epoch

    def add_knowledge_snapshot(
        self,
        snapshot: KnowledgeSnapshot,
        version_sources: dict[str, str],
    ) -> None:
        """中文：持久化查询租约和其精确文档版本集。

        English: Persist a query lease and its exact document-version membership.
        """

        if set(version_sources) != set(snapshot.document_version_ids):
            raise ValueError("snapshot version/source mapping is incomplete")
        self._session.add(
            QuerySnapshotRow(
                id=snapshot.id,
                tenant_id=snapshot.tenant_id,
                user_id=snapshot.user_id,
                status=snapshot.status.value,
                index_version_id=snapshot.index_version_id,
                index_manifest_fingerprint=snapshot.index_manifest_fingerprint,
                authorization_fingerprint=snapshot.authorization_fingerprint,
                captured_revocation_epoch=snapshot.captured_revocation_epoch,
                source_ids_json=sorted(snapshot.source_ids),
                created_at=snapshot.created_at,
                expires_at=snapshot.expires_at,
                closed_at=snapshot.closed_at,
            )
        )
        self._session.flush()
        self._session.add_all(
            QuerySnapshotDocumentVersionRow(
                snapshot_id=snapshot.id,
                document_version_id=version_id,
                source_id=source_id,
            )
            for version_id, source_id in sorted(version_sources.items())
        )
        self._session.flush()

    def close_knowledge_snapshot(self, tenant_id: str, snapshot_id: str, now: datetime) -> None:
        """中文：将问答快照租约幂等地关闭，物理清理可继续执行。

        English: Idempotently close a query snapshot lease so physical cleanup may proceed.
        """

        self._session.execute(
            update(QuerySnapshotRow)
            .where(
                QuerySnapshotRow.tenant_id == tenant_id,
                QuerySnapshotRow.id == snapshot_id,
                QuerySnapshotRow.status == SnapshotStatus.ACTIVE.value,
            )
            .values(status=SnapshotStatus.CLOSED.value, closed_at=now)
        )
        self._session.flush()

    def record_revocation(
        self,
        tenant_id: str,
        scope_type: RevocationScopeType,
        scope_id: str,
        reason_code: str,
        requested_by: str,
        now: datetime,
    ) -> RevocationRecord:
        """中文：原子递增租户 epoch 并记录可立即覆盖旧快照的撤销事件。

        English: Atomically increment the tenant epoch and record a revocation overriding old
        snapshots.
        """

        current = self._session.get(TenantKnowledgeStateRow, tenant_id)
        if current is None:
            current = TenantKnowledgeStateRow(tenant_id=tenant_id, revocation_epoch=0)
            self._session.add(current)
            self._session.flush()
        new_epoch = self._session.scalar(
            update(TenantKnowledgeStateRow)
            .where(TenantKnowledgeStateRow.tenant_id == tenant_id)
            .values(revocation_epoch=TenantKnowledgeStateRow.revocation_epoch + 1, updated_at=now)
            .returning(TenantKnowledgeStateRow.revocation_epoch)
        )
        if new_epoch is None:
            raise RuntimeError("failed to allocate revocation epoch")
        record = RevocationRecord(
            id=new_id("rvk"),
            tenant_id=tenant_id,
            epoch=new_epoch,
            scope_type=scope_type,
            scope_id=scope_id,
            reason_code=reason_code,
            requested_by=requested_by,
            created_at=now,
        )
        self._session.add(
            RevocationRow(
                id=record.id,
                tenant_id=record.tenant_id,
                epoch=record.epoch,
                scope_type=record.scope_type.value,
                scope_id=record.scope_id,
                reason_code=record.reason_code,
                requested_by=record.requested_by,
                created_at=record.created_at,
            )
        )
        self._session.flush()
        return record

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
                snapshot_id=trace.snapshot_id,
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
        next_version_number=row.next_version_number or 2,
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
        chunk_strategy_version=str(snapshot.get("chunk_strategy_version", "general-prose-v1")),
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
        original_locator_json=(
            _original_locator_to_json(chunk.locator) if chunk.locator is not None else None
        ),
        display_locator_json=(
            _display_locator_to_json(chunk.locator) if chunk.locator is not None else None
        ),
        normalized_start=(chunk.locator.normalized.start if chunk.locator else None),
        normalized_end=(chunk.locator.normalized.end if chunk.locator else None),
        locator_mapping_quality=(chunk.locator.mapping_quality.value if chunk.locator else None),
        structure_node_id=chunk.structure_node_id,
        structure_type=(chunk.structure_type.value if chunk.structure_type else None),
        hard_boundary_key=chunk.hard_boundary_key,
    )


def _chunk_from_row(row: ChunkRow) -> Chunk:
    """中文：该内部函数负责“文本块从数据行”相关处理。

    English: Map a persistence chunk row to an immutable domain entity.
    """

    # 中文：V4 之前的数据缺少新增键时使用安全默认值，无需破坏性迁移。
    # English: Safe defaults keep pre-V4 rows readable without a destructive migration.
    metadata = _json_mapping(row.extra_metadata)
    locator = _locator_from_row(row)
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
        locator=locator,
        structure_node_id=row.structure_node_id,
        structure_type=(StructureType(row.structure_type) if row.structure_type else None),
        hard_boundary_key=row.hard_boundary_key,
    )


def _original_locator_to_json(locator: LocatorBundle) -> dict[str, object]:
    """中文：把原文件 Locator 转换为稳定 JSON 映射。

    English: Serialize an original-file locator into a stable JSON mapping.
    """

    return {
        "page_start": locator.original.page_start,
        "page_end": locator.original.page_end,
        "block_ids": list(locator.original.block_ids),
        "line_start": locator.original.line_start,
        "line_end": locator.original.line_end,
        "ocr_boxes": [
            {
                "page": box.page,
                "left": box.left,
                "top": box.top,
                "right": box.right,
                "bottom": box.bottom,
            }
            for box in locator.original.ocr_boxes
        ],
    }


def _display_locator_to_json(locator: LocatorBundle) -> dict[str, object]:
    """中文：把用户展示 Locator 转换为稳定 JSON 映射。

    English: Serialize a user-facing locator into a stable JSON mapping.
    """

    return {
        "title": locator.display.title,
        "heading_path": list(locator.display.heading_path),
        "structural_anchor": locator.display.structural_anchor,
        "page_start": locator.display.page_start,
        "page_end": locator.display.page_end,
    }


def _locator_from_row(row: ChunkRow) -> LocatorBundle | None:
    """中文：从 V5 坐标列恢复 Locator；旧 Chunk 缺列值时返回空。

    English: Restore a locator from V5 columns and return none for legacy chunk values.
    """

    if (
        row.original_locator_json is None
        or row.display_locator_json is None
        or row.normalized_start is None
        or row.normalized_end is None
        or row.locator_mapping_quality is None
    ):
        return None
    original = _json_mapping(row.original_locator_json)
    display = _json_mapping(row.display_locator_json)
    return LocatorBundle(
        original=OriginalLocator(
            page_start=_optional_int(original.get("page_start")),
            page_end=_optional_int(original.get("page_end")),
            block_ids=_string_tuple(original.get("block_ids")),
            line_start=_optional_int(original.get("line_start")),
            line_end=_optional_int(original.get("line_end")),
            ocr_boxes=_ocr_boxes(original.get("ocr_boxes")),
        ),
        normalized=NormalizedRange(row.normalized_start, row.normalized_end),
        display=DisplayLocator(
            title=(str(display["title"]) if display.get("title") is not None else None),
            heading_path=_string_tuple(display.get("heading_path")),
            structural_anchor=(
                str(display["structural_anchor"])
                if display.get("structural_anchor") is not None
                else None
            ),
            page_start=_optional_int(display.get("page_start")),
            page_end=_optional_int(display.get("page_end")),
        ),
        mapping_quality=LocatorMappingQuality(row.locator_mapping_quality),
    )


def _optional_int(value: object) -> int | None:
    """中文：仅把真实整数或整数字符串转换为可选整数。

    English: Convert only genuine integers or integer strings into an optional integer.
    """

    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _string_tuple(value: object) -> tuple[str, ...]:
    """中文：把 JSON 数组安全收窄为字符串元组。

    English: Safely narrow a JSON array into a tuple of strings.
    """

    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(item) for item in value)


def _ocr_boxes(value: object) -> tuple[OCRBox, ...]:
    """中文：从经过边界校验的 JSON 对象恢复有效 OCR 矩形。

    English: Restore valid OCR rectangles from boundary-checked JSON objects.
    """

    if not isinstance(value, list):
        return ()
    boxes: list[OCRBox] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        try:
            boxes.append(
                OCRBox(
                    page=int(item["page"]),
                    left=float(item["left"]),
                    top=float(item["top"]),
                    right=float(item["right"]),
                    bottom=float(item["bottom"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return tuple(boxes)


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
        idempotency_key=row.idempotency_key,
        job_type=JobType(row.job_type),
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
        snapshot_id=row.snapshot_id,
        attributes=row.attributes,
        created_at=row.created_at,
        completed_at=row.completed_at,
    )
