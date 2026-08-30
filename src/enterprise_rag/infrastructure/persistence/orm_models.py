"""中文：本模块负责实现“`orm`模型”相关功能。

English: Declare normalized SQLAlchemy tables for tenant data, jobs, indexes, and traces.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from enterprise_rag.core.enums import ContentProfile, DocumentStatus, IndexStatus, JobStatus
from enterprise_rag.domain.models import utc_now


class Base(DeclarativeBase):
    """中文：该类用于表示或实现“基础（Base）”的职责。

    English: Provide shared SQLAlchemy metadata for all persistence tables.
    """


class TenantRow(Base):
    """中文：该类用于表示或实现“租户数据行（TenantRow）”的职责。

    English: Persist an isolated customer organization.
    """

    __tablename__ = "tenants"

    # 中文：变量 `id` 用于保存“标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable tenant primary key.
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    # 中文：变量 `name` 用于保存“`name`”相关数据；其精确定义与约束见下方英文说明。
    # English: Human-readable organization name.
    name: Mapped[str] = mapped_column(String(255))
    # 中文：变量 `is_active` 用于保存“`is`活动”相关数据；其精确定义与约束见下方英文说明。
    # English: Soft operational switch.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # 中文：变量 `created_at` 用于保存“`created``at`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Audit creation time.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SourceRow(Base):
    """中文：该类用于表示或实现“资料源数据行（SourceRow）”的职责。

    English: Persist a routable and permission-aware knowledge source.
    """

    __tablename__ = "sources"
    __table_args__ = (Index("ix_sources_tenant_active", "tenant_id", "is_active"),)

    # 中文：变量 `id` 用于保存“标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable source primary key.
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    # 中文：变量 `tenant_id` 用于保存“租户标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Owning tenant foreign key.
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    # 中文：变量 `name` 用于保存“`name`”相关数据；其精确定义与约束见下方英文说明。
    # English: Display name.
    name: Mapped[str] = mapped_column(String(255))
    # 中文：变量 `description` 用于保存“`description`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Routing description.
    description: Mapped[str] = mapped_column(Text, default="")
    # 中文：资料源级内容画像用于稳定选择结构识别与切块策略。
    # English: Source-level content profile deterministically selects structure/chunk rules.
    content_profile: Mapped[str] = mapped_column(
        String(32), default=ContentProfile.GENERAL_PROSE.value, nullable=False
    )
    # 中文：高级管理员可选的策略覆盖；默认由内容画像注册表解析。
    # English: Optional advanced strategy override; profiles resolve it by default.
    chunk_strategy_override: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # 中文：变量 `visibility` 用于保存“`visibility`”相关数据；其精确定义与约束见下方英文说明。
    # English: SourceVisibility serialized value.
    visibility: Mapped[str] = mapped_column(String(32))
    # 中文：变量 `allowed_group_ids` 用于保存“`allowed``group`标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: JSON array of permitted group IDs.
    allowed_group_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    # 中文：变量 `is_active` 用于保存“`is`活动”相关数据；其精确定义与约束见下方英文说明。
    # English: Whether new scopes may include the source.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # 中文：变量 `created_at` 用于保存“`created``at`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Audit creation time.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DocumentRow(Base):
    """中文：该类用于表示或实现“文档数据行（DocumentRow）”的职责。

    English: Persist lifecycle state for one logical document.
    """

    __tablename__ = "documents"
    __table_args__ = (Index("ix_documents_tenant_status", "tenant_id", "status"),)

    # 中文：变量 `id` 用于保存“标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable logical document primary key.
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    # 中文：变量 `tenant_id` 用于保存“租户标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Owning tenant foreign key.
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    # 中文：变量 `source_id` 用于保存“资料源标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Parent source foreign key.
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    # 中文：变量 `title` 用于保存“标题”相关数据；其精确定义与约束见下方英文说明。
    # English: Safe display title.
    title: Mapped[str] = mapped_column(String(512))
    # 中文：变量 `status` 用于保存“状态”相关数据；其精确定义与约束见下方英文说明。
    # English: Serialized DocumentStatus value.
    status: Mapped[str] = mapped_column(String(32), default=DocumentStatus.PENDING.value)
    # 中文：变量 `active_version_id` 用于保存“活动版本标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Active immutable version, intentionally added without circular foreign-key
    #   enforcement.
    active_version_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # 中文：删除时原子递增，用于阻断所有旧任务和旧索引发布计划。
    # English: Atomically incremented on deletion to fence every stale job and publication plan.
    lifecycle_generation: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # 中文：删除请求和完成时间把逻辑状态与物理清理过程分开记录。
    # English: Request/completion timestamps separate logical state from physical cleanup.
    delete_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 中文：变量 `created_at` 用于保存“`created``at`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Audit creation time.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    # 中文：变量 `updated_at` 用于保存“`updated``at`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Last lifecycle update time.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class DocumentVersionRow(Base):
    """中文：该类用于表示或实现“文档版本数据行（DocumentVersionRow）”的职责。

    English: Persist immutable original-file metadata for one document version.
    """

    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_document_version_number"),
    )

    # 中文：变量 `id` 用于保存“标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable document-version primary key.
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    # 中文：变量 `tenant_id` 用于保存“租户标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Owning tenant foreign key.
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    # 中文：变量 `document_id` 用于保存“文档标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Logical parent document foreign key.
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    # 中文：变量 `source_id` 用于保存“资料源标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Parent source copied for efficient authorization.
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    # 中文：变量 `version_number` 用于保存“版本`number`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Monotonic version number.
    version_number: Mapped[int] = mapped_column(Integer)
    # 中文：变量 `original_filename` 用于保存“原始`filename`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Display-only original filename.
    original_filename: Mapped[str] = mapped_column(String(512))
    # 中文：变量 `media_type` 用于保存“`media``type`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Verified document media type.
    media_type: Mapped[str] = mapped_column(String(64))
    # 中文：变量 `content_hash` 用于保存“`content``hash`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: SHA-256 original file checksum.
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    # 中文：变量 `storage_key` 用于保存“存储`key`”相关数据；其精确定义与约束见下方英文说明。
    # English: Opaque file-store key.
    storage_key: Mapped[str] = mapped_column(String(512))
    # 中文：变量 `size_bytes` 用于保存“`size``bytes`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Original file byte length.
    size_bytes: Mapped[int] = mapped_column(Integer)
    # 中文：变量 `ingestion_snapshot` 冻结内容画像、策略、模型与质量指标。
    # English: `ingestion_snapshot` freezes profile, strategy, model, and quality metadata.
    ingestion_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    # 中文：变量 `created_at` 用于保存“`created``at`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Audit creation time.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ChunkRow(Base):
    """中文：该类用于表示或实现“文本块数据行（ChunkRow）”的职责。

    English: Persist deterministic citable text and positional metadata.
    """

    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_version_id", "ordinal", name="uq_chunk_version_ordinal"),
        Index("ix_chunks_scope", "tenant_id", "source_id", "document_id"),
    )

    # 中文：变量 `id` 用于保存“标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Deterministic chunk primary key.
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    # 中文：变量 `tenant_id` 用于保存“租户标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Owning tenant foreign key.
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    # 中文：变量 `source_id` 用于保存“资料源标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Parent source foreign key.
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    # 中文：变量 `document_id` 用于保存“文档标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Logical document foreign key.
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    # 中文：变量 `document_version_id` 用于保存“文档版本标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Immutable document-version foreign key.
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("document_versions.id"),
        index=True,
    )
    # 中文：变量 `ordinal` 用于保存“`ordinal`”相关数据；其精确定义与约束见下方英文说明。
    # English: Zero-based order within the version.
    ordinal: Mapped[int] = mapped_column(Integer)
    # 中文：变量 `text` 用于保存“文本”相关数据；其精确定义与约束见下方英文说明。
    # English: Normalized chunk text.
    text: Mapped[str] = mapped_column(Text)
    # 中文：变量 `token_count` 用于保存“词元`count`”相关数据；其精确定义与约束见下方英文说明。
    # English: Token estimate.
    token_count: Mapped[int] = mapped_column(Integer)
    # 中文：变量 `page_start` 用于保存“`page``start`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: First represented page.
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 中文：变量 `page_end` 用于保存“`page``end`”相关数据；其精确定义与约束见下方英文说明。
    # English: Last represented page.
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 中文：变量 `heading_path` 用于保存“`heading``path`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: JSON array of hierarchical headings.
    heading_path: Mapped[list[str]] = mapped_column(JSON, default=list)
    # 中文：变量 `previous_chunk_id` 用于保存“`previous`文本块标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Previous deterministic chunk ID.
    previous_chunk_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # 中文：变量 `next_chunk_id` 用于保存“下一个文本块标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Next deterministic chunk ID.
    next_chunk_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # 中文：变量 `boundary_reason` 用于保存“`boundary`原因”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Human-readable boundary reason.
    boundary_reason: Mapped[str] = mapped_column(String(64))
    # 中文：变量 `chunker_version` 用于保存“切块器版本”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Chunker version.
    chunker_version: Mapped[str] = mapped_column(String(128))
    # 中文：变量 `content_hash` 用于保存“`content``hash`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Normalized chunk checksum.
    content_hash: Mapped[str] = mapped_column(String(64))
    # 中文：变量 `extra_metadata` 用于保存“`extra`元数据”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Safe parser-specific metadata.
    extra_metadata: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)


class IngestionJobRow(Base):
    """中文：该类用于表示或实现“资料接入任务数据行（IngestionJobRow）”的职责。

    English: Persist a lease-based recoverable ingestion task.
    """

    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        CheckConstraint("attempt_count >= 0", name="ck_ingestion_jobs_attempt_nonnegative"),
        Index("ix_jobs_claim", "status", "lease_expires_at", "created_at"),
    )

    # 中文：变量 `id` 用于保存“标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable job primary key.
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    # 中文：变量 `tenant_id` 用于保存“租户标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Owning tenant foreign key.
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    # 中文：变量 `document_id` 用于保存“文档标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Logical document foreign key.
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    # 中文：变量 `document_version_id` 用于保存“文档版本标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Immutable version foreign key.
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("document_versions.id"),
        index=True,
    )
    # 中文：入队时文档 generation 快照，与 Worker 租约代次共同构成 fencing token。
    # English: Enqueue-time document generation combines with the lease attempt as a fence.
    document_generation_snapshot: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # 中文：变量 `status` 用于保存“状态”相关数据；其精确定义与约束见下方英文说明。
    # English: Serialized JobStatus value.
    status: Mapped[str] = mapped_column(String(32), default=JobStatus.PENDING.value)
    # 中文：变量 `attempt_count` 用于保存“`attempt``count`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Number of worker claims.
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    # 中文：变量 `lease_owner` 用于保存“`lease``owner`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Current worker lease owner.
    lease_owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # 中文：变量 `lease_expires_at` 用于保存“`lease``expires``at`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Lease recovery deadline.
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    # 中文：变量 `error_code` 用于保存“错误`code`”相关数据；其精确定义与约束见下方英文说明。
    # English: Safe stable failure code.
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # 中文：变量 `error_message` 用于保存“错误消息”相关数据；其精确定义与约束见下方英文说明。
    # English: Safe redacted failure message.
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 中文：运行任务在阶段检查点读取持久取消标志并安全收口。
    # English: Running jobs observe durable cancellation at stage checkpoints and stop safely.
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancel_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # 中文：变量 `created_at` 用于保存“`created``at`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: FIFO creation time.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    # 中文：变量 `updated_at` 用于保存“`updated``at`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Last durable update time.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class IndexVersionRow(Base):
    """中文：该类用于表示或实现“索引版本数据行（IndexVersionRow）”的职责。

    English: Persist publication metadata for an immutable index snapshot.
    """

    __tablename__ = "index_versions"
    __table_args__ = (Index("ix_index_tenant_status_created", "tenant_id", "status", "created_at"),)

    # 中文：变量 `id` 用于保存“标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable index-version primary key.
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    # 中文：变量 `tenant_id` 用于保存“租户标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Owning tenant foreign key.
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    # 中文：变量 `status` 用于保存“状态”相关数据；其精确定义与约束见下方英文说明。
    # English: Serialized IndexStatus value.
    status: Mapped[str] = mapped_column(String(32), default=IndexStatus.STAGING.value)
    # 中文：变量 `storage_key` 用于保存“存储`key`”相关数据；其精确定义与约束见下方英文说明。
    # English: Opaque snapshot directory key.
    storage_key: Mapped[str] = mapped_column(String(512))
    # 中文：变量 `chunk_count` 用于保存“文本块`count`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Number of chunks represented by every index component.
    chunk_count: Mapped[int] = mapped_column(Integer)
    # 中文：变量 `config_fingerprint` 用于保存“配置指纹”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Configuration and model fingerprint.
    config_fingerprint: Mapped[str] = mapped_column(String(128))
    # 中文：变量 `created_at` 用于保存“`created``at`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Snapshot creation time.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    # 中文：变量 `activated_at` 用于保存“`activated``at`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Transactional activation time.
    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    # 中文：候选发布失败和取消必须保存终态原因，避免永久 STAGING。
    # English: Failed and cancelled candidates persist terminal reasons and never remain STAGING.
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class TraceRow(Base):
    """中文：该类用于表示或实现“追踪数据行（TraceRow）”的职责。

    English: Persist a redacted workflow trace summary.
    """

    __tablename__ = "traces"
    __table_args__ = (Index("ix_traces_tenant_user", "tenant_id", "user_id", "created_at"),)

    # 中文：变量 `id` 用于保存“标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable trace primary key.
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    # 中文：变量 `tenant_id` 用于保存“租户标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Owning tenant foreign key.
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    # 中文：变量 `user_id` 用于保存“用户标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Requesting user identifier.
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    # 中文：变量 `operation` 用于保存“`operation`”相关数据；其精确定义与约束见下方英文说明。
    # English: Workflow type.
    operation: Mapped[str] = mapped_column(String(64))
    # 中文：变量 `status` 用于保存“状态”相关数据；其精确定义与约束见下方英文说明。
    # English: Final or current status.
    status: Mapped[str] = mapped_column(String(32))
    # 中文：变量 `index_version_id` 用于保存“索引版本标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Pinned immutable index snapshot when applicable.
    index_version_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # 中文：变量 `attributes` 用于保存“`attributes`”相关数据；其精确定义与约束见下方英文说明。
    # English: Safe structured trace attributes.
    attributes: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    # 中文：变量 `created_at` 用于保存“`created``at`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Trace creation time.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    # 中文：变量 `completed_at` 用于保存“`completed``at`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Terminal completion time.
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
