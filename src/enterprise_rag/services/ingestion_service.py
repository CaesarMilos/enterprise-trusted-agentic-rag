"""中文：本模块负责实现“资料接入服务”相关功能。

English: Accept validated uploads, persist original bytes, and create durable ingestion jobs.
"""

from __future__ import annotations

from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from enterprise_rag.core.enums import ContentProfile, DocumentStatus, ErrorCategory, JobStatus
from enterprise_rag.core.exceptions import PermissionDeniedError, ValidationError, error_detail
from enterprise_rag.core.ids import new_id
from enterprise_rag.domain.models import Document, DocumentVersion, IngestionJob
from enterprise_rag.domain.protocols.storage import FileStore
from enterprise_rag.domain.requests import (
    CreateDocumentCommand,
    ReprocessDocumentCommand,
    RetryIngestionCommand,
)
from enterprise_rag.domain.results import IngestionAccepted
from enterprise_rag.infrastructure.persistence.database import transactional_session
from enterprise_rag.infrastructure.persistence.orm_models import (
    DocumentVersionRow,
    IngestionJobRow,
)
from enterprise_rag.infrastructure.persistence.repositories import SQLAlchemyRepositories
from enterprise_rag.ingestion.chunk_strategies import ChunkStrategyRegistry
from enterprise_rag.ingestion.validator import UploadValidator


class _VersionSnapshotFields(TypedDict):
    """中文：精确描述 DocumentVersion 构造器展开的冻结策略字段。

    English: Precisely type frozen strategy fields expanded into DocumentVersion construction.
    """

    content_profile: ContentProfile
    chunk_strategy_id: str
    chunk_strategy_version: str
    chunk_parameters: dict[str, object]
    embedding_fingerprint: str
    boundary_model_fingerprint: str | None


class IngestionService:
    """中文：该类用于表示或实现“资料接入服务（IngestionService）”的职责。

    English: Create a document, immutable version, stored file, and durable job as one use case.
    """

    def __init__(
        self,
        sessions: sessionmaker[Session],
        validator: UploadValidator,
        file_store: FileStore,
        strategy_registry: ChunkStrategyRegistry | None = None,
        chunk_parameters: dict[str, object] | None = None,
        embedding_fingerprint: str = "",
        boundary_model_fingerprint: str | None = None,
    ) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store transaction, validation, and original-file dependencies.
        """

        # 中文：变量 `_sessions` 用于保存“`sessions`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Session factory creates one metadata transaction per upload.
        self._sessions = sessions
        # 中文：变量 `_validator` 用于保存“校验器”相关数据；其精确定义与约束见下方英文说明。
        # English: Validator rejects unsupported or spoofed files before durable writes.
        self._validator = validator
        # 中文：变量 `_file_store` 用于保存“文件存储”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: File store owns opaque tenant-isolated paths.
        self._file_store = file_store
        # 中文：以下依赖在任务创建时冻结策略，避免排队期间 Source 配置发生漂移。
        # English: These dependencies freeze strategy state when a job is created, preventing
        # Source configuration drift while queued.
        self._strategy_registry = strategy_registry
        self._chunk_parameters = dict(chunk_parameters or {})
        self._embedding_fingerprint = embedding_fingerprint
        self._boundary_model_fingerprint = boundary_model_fingerprint

    def create_document(self, command: CreateDocumentCommand) -> IngestionAccepted:
        """中文：该函数或方法负责“创建文档”相关处理。

        English: Persist an accepted upload and return its durable asynchronous job identity.
        """

        # 中文：本步骤涉及资料源、已授权、上传，具体约束见下方英文说明。
        # English: Only administrators or explicitly source-authorized users may upload to
        #   a source.
        if not command.user.is_admin() and command.source_id not in command.user.allowed_source_ids:
            raise PermissionDeniedError(
                error_detail(
                    "SOURCE_UPLOAD_DENIED",
                    ErrorCategory.PERMISSION,
                    "The user may not upload documents to this source.",
                )
            )
        # 中文：变量 `validated` 用于保存“`validated`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Validation occurs before generating persistent domain entities.
        validated = self._validator.validate(command.temporary_path, command.filename)
        # 中文：变量 `document_id` 用于保存“文档标识符”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Independent random IDs identify the logical document, version, and
        #   background job.
        document_id = new_id("doc")
        version_id = new_id("ver")
        job_id = new_id("job")
        # 中文：本步骤涉及结果、元数据、事务，具体约束见下方英文说明。
        # English: Stored result is created before metadata but deleted if the transaction
        #   fails.
        with validated.path.open("rb") as source:
            stored = self._file_store.save(
                command.user.tenant_id,
                version_id,
                validated.filename,
                source,
            )
        try:
            with transactional_session(self._sessions) as session:
                repositories = SQLAlchemyRepositories(session)
                # 中文：变量 `source_entity` 用于保存“资料源`entity`”相关数据；
                # 其精确定义与约束见下方英文说明。
                # English: Source lookup applies tenant isolation and prevents orphan
                #   document creation.
                source_entity = repositories.get_source(
                    command.user.tenant_id,
                    command.source_id,
                )
                if source_entity is None or not source_entity.is_active:
                    raise ValidationError(
                        error_detail(
                            "SOURCE_NOT_FOUND",
                            ErrorCategory.VALIDATION,
                            "The target source does not exist or is inactive.",
                        )
                    )
                document = Document(
                    id=document_id,
                    tenant_id=command.user.tenant_id,
                    source_id=command.source_id,
                    title=command.title or validated.filename,
                    status=DocumentStatus.PENDING,
                )
                version = DocumentVersion(
                    id=version_id,
                    tenant_id=command.user.tenant_id,
                    document_id=document_id,
                    source_id=command.source_id,
                    version_number=1,
                    original_filename=validated.filename,
                    media_type=validated.media_type,
                    content_hash=stored.content_hash,
                    storage_key=stored.storage_key,
                    size_bytes=stored.size_bytes,
                    **self._snapshot_fields(
                        source_entity.content_profile,
                        source_entity.chunk_strategy_override,
                    ),
                )
                job = IngestionJob(
                    id=job_id,
                    tenant_id=command.user.tenant_id,
                    document_id=document_id,
                    document_version_id=version_id,
                    document_generation_snapshot=document.lifecycle_generation,
                    status=JobStatus.PENDING,
                )
                repositories.add_document(document)
                repositories.add_version(version)
                repositories.add_job(job)
        except Exception:
            # 中文：本步骤涉及清理、元数据，具体约束见下方英文说明。
            # English: Exact opaque key cleanup prevents orphan bytes after metadata
            #   rollback.
            self._file_store.delete(command.user.tenant_id, stored.storage_key)
            raise
        return IngestionAccepted(
            document_id=document_id,
            document_version_id=version_id,
            job_id=job_id,
            status=DocumentStatus.PENDING.value,
        )

    def retry(self, command: RetryIngestionCommand) -> IngestionAccepted:
        """中文：该函数或方法负责“重试”相关处理。

        English: Create a fresh durable job for the current failed document version.
        """

        if not command.user.is_admin():
            raise PermissionDeniedError(
                error_detail(
                    "INGESTION_RETRY_DENIED",
                    ErrorCategory.PERMISSION,
                    "Only tenant administrators may retry ingestion.",
                )
            )
        # 中文：变量 `job_id` 用于保存“任务标识符”相关数据；其精确定义与约束见下方英文说明。
        # English: Fresh job ID preserves failed-attempt history.
        job_id = new_id("job")
        with transactional_session(self._sessions) as session:
            repositories = SQLAlchemyRepositories(session)
            document = repositories.get_document(
                command.user.tenant_id,
                command.document_id,
            )
            if document is None:
                raise ValidationError(
                    error_detail(
                        "DOCUMENT_NOT_RETRYABLE",
                        ErrorCategory.VALIDATION,
                        "The document does not exist or cannot be retried.",
                    )
                )
            if document.status in {DocumentStatus.PENDING_DELETE, DocumentStatus.DELETED}:
                raise ValidationError(
                    error_detail(
                        "DOCUMENT_NOT_RETRYABLE",
                        ErrorCategory.VALIDATION,
                        "A deleting or deleted document cannot be retried.",
                    )
                )
            # 中文：关键变量 `failed_job_row` 选择最新失败候选任务，而非假设逻辑文档也失败。
            # English: Key variable `failed_job_row` selects the latest failed candidate job
            # instead of assuming the logical document also failed.
            failed_job_row = session.scalar(
                select(IngestionJobRow)
                .where(
                    IngestionJobRow.tenant_id == command.user.tenant_id,
                    IngestionJobRow.document_id == command.document_id,
                    IngestionJobRow.status.in_(
                        (
                            JobStatus.FAILED.value,
                            JobStatus.NEEDS_OCR.value,
                            JobStatus.NEEDS_REVIEW.value,
                        )
                    ),
                )
                .order_by(IngestionJobRow.created_at.desc(), IngestionJobRow.id.desc())
                .limit(1)
            )
            if failed_job_row is None:
                raise ValidationError(
                    error_detail(
                        "DOCUMENT_NOT_RETRYABLE",
                        ErrorCategory.VALIDATION,
                        "The document has no failed ingestion candidate to retry.",
                    )
                )
            version = repositories.get_version(
                command.user.tenant_id,
                failed_job_row.document_version_id,
            )
            if version is None:
                raise ValidationError(
                    error_detail(
                        "DOCUMENT_VERSION_NOT_FOUND",
                        ErrorCategory.VALIDATION,
                        "The failed ingestion candidate has no stored version.",
                    )
                )
            repositories.add_job(
                IngestionJob(
                    id=job_id,
                    tenant_id=command.user.tenant_id,
                    document_id=document.id,
                    document_version_id=version.id,
                    document_generation_snapshot=document.lifecycle_generation,
                    status=JobStatus.PENDING,
                )
            )
            # 中文：已有活动版本保持 READY；只有从未成功发布过的文档回到 PENDING。
            # English: Preserve READY for an active version; only never-published documents
            # return to PENDING.
            if document.active_version_id is None:
                repositories.set_document_status(
                    command.user.tenant_id,
                    document.id,
                    DocumentStatus.PENDING,
                )
        return IngestionAccepted(
            document_id=document.id,
            document_version_id=version.id,
            job_id=job_id,
            status=(
                DocumentStatus.READY.value
                if document.active_version_id is not None
                else DocumentStatus.PENDING.value
            ),
        )

    def reprocess(self, command: ReprocessDocumentCommand) -> IngestionAccepted:
        """中文：复用原始文件创建新文档版本，并按当前 Source 画像重新切块。

        English: Create a new version over the original file and re-chunk with current profile.
        """

        if not command.user.is_admin():
            raise PermissionDeniedError(
                error_detail(
                    "DOCUMENT_REPROCESS_DENIED",
                    ErrorCategory.PERMISSION,
                    "Only tenant administrators may reprocess documents.",
                )
            )
        # 中文：新版本和新任务保留旧版本、旧 Chunk 与旧索引的可追溯性。
        # English: New version/job IDs preserve old versions, chunks, and index traceability.
        version_id = new_id("ver")
        job_id = new_id("job")
        with transactional_session(self._sessions) as session:
            repositories = SQLAlchemyRepositories(session)
            document = repositories.get_document(
                command.user.tenant_id,
                command.document_id,
            )
            if document is None:
                raise ValidationError(
                    error_detail(
                        "DOCUMENT_NOT_FOUND",
                        ErrorCategory.VALIDATION,
                        "The document does not exist.",
                    )
                )
            if document.status in {DocumentStatus.PENDING_DELETE, DocumentStatus.DELETED}:
                raise ValidationError(
                    error_detail(
                        "DOCUMENT_NOT_REPROCESSABLE",
                        ErrorCategory.VALIDATION,
                        "A deleting or deleted document cannot be reprocessed.",
                    )
                )
            source = repositories.get_source(command.user.tenant_id, document.source_id)
            if source is None or not source.is_active:
                raise ValidationError(
                    error_detail(
                        "SOURCE_NOT_FOUND",
                        ErrorCategory.VALIDATION,
                        "The document source does not exist or is inactive.",
                    )
                )
            latest = session.scalar(
                select(DocumentVersionRow)
                .where(
                    DocumentVersionRow.tenant_id == command.user.tenant_id,
                    DocumentVersionRow.document_id == command.document_id,
                )
                .order_by(DocumentVersionRow.version_number.desc())
                .limit(1)
            )
            if latest is None:
                raise ValidationError(
                    error_detail(
                        "DOCUMENT_VERSION_NOT_FOUND",
                        ErrorCategory.VALIDATION,
                        "The document has no original version to reprocess.",
                    )
                )
            version = DocumentVersion(
                id=version_id,
                tenant_id=latest.tenant_id,
                document_id=latest.document_id,
                source_id=latest.source_id,
                version_number=latest.version_number + 1,
                original_filename=latest.original_filename,
                media_type=latest.media_type,
                content_hash=latest.content_hash,
                storage_key=latest.storage_key,
                size_bytes=latest.size_bytes,
                **self._snapshot_fields(
                    source.content_profile,
                    source.chunk_strategy_override,
                ),
            )
            repositories.add_version(version)
            repositories.add_job(
                IngestionJob(
                    id=job_id,
                    tenant_id=command.user.tenant_id,
                    document_id=document.id,
                    document_version_id=version_id,
                    document_generation_snapshot=document.lifecycle_generation,
                    status=JobStatus.PENDING,
                )
            )
            # 中文：已有活动版本继续保持 READY，新候选版本在任务中独立处理。
            # English: An existing active version remains READY while the candidate is processed.
            if document.active_version_id is None:
                repositories.set_document_status(
                    command.user.tenant_id,
                    document.id,
                    DocumentStatus.PENDING,
                )
        return IngestionAccepted(
            document_id=command.document_id,
            document_version_id=version_id,
            job_id=job_id,
            status=(
                DocumentStatus.READY.value
                if document.active_version_id is not None
                else DocumentStatus.PENDING.value
            ),
        )

    def _snapshot_fields(
        self,
        content_profile: ContentProfile,
        strategy_override: str | None,
    ) -> _VersionSnapshotFields:
        """中文：解析并返回写入 DocumentVersion 的不可变接入策略快照字段。

        English: Resolve and return immutable ingestion-strategy fields for DocumentVersion.
        """

        profile = content_profile
        if self._strategy_registry is not None:
            strategy = self._strategy_registry.resolve(profile, strategy_override)
            strategy_id = strategy.strategy_id
            strategy_version = strategy.version
        else:
            # 中文：兼容简化单元测试构造方式；生产容器始终注入注册表。
            # English: Preserve simple unit-test construction; production always injects registry.
            strategy_id = strategy_override or {
                ContentProfile.GENERAL_PROSE: "general-prose",
                ContentProfile.MANUAL: "manual-structure",
                ContentProfile.TECHNICAL_DOC: "technical-document",
                ContentProfile.REGULATION: "regulation-structure",
                ContentProfile.ACADEMIC: "academic-structure",
                ContentProfile.NARRATIVE: "narrative-structure",
            }[profile]
            strategy_version = f"{strategy_id}-v4"
        return {
            "content_profile": profile,
            "chunk_strategy_id": strategy_id,
            "chunk_strategy_version": strategy_version,
            "chunk_parameters": dict(self._chunk_parameters),
            "embedding_fingerprint": self._embedding_fingerprint,
            "boundary_model_fingerprint": self._boundary_model_fingerprint,
        }
