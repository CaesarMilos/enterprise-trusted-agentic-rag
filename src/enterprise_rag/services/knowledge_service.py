"""中文：本模块负责实现“知识服务”相关功能。

English: Build tenant index snapshots and coordinate document query and deletion lifecycles.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from enterprise_rag.core.enums import (
    ContentProfile,
    DocumentStatus,
    ErrorCategory,
    IndexStatus,
    JobStatus,
    JobType,
    RevocationScopeType,
)
from enterprise_rag.core.exceptions import (
    JobCancelledError,
    LeaseLostError,
    LifecycleFenceError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
    error_detail,
)
from enterprise_rag.core.ids import new_id
from enterprise_rag.domain.models import (
    Chunk,
    IndexVersion,
    IngestionJob,
    JobFence,
    UserContext,
)
from enterprise_rag.domain.results import (
    DeletionAccepted,
    DocumentDetail,
    IndexBuildResult,
    JobDetail,
)
from enterprise_rag.indexing.index_coordinator import IndexCoordinator
from enterprise_rag.indexing.models import IndexBuildPlan
from enterprise_rag.infrastructure.persistence.database import transactional_session
from enterprise_rag.infrastructure.persistence.repositories import SQLAlchemyRepositories
from enterprise_rag.ingestion.chunk_strategies import ChunkStrategyRegistry


class IndexBuildService:
    """中文：该类用于表示或实现“索引构建服务（IndexBuildService）”的职责。

    English: Create one shared BuildPlan and publish its components as an immutable snapshot.
    """

    def __init__(
        self,
        sessions: sessionmaker[Session],
        coordinator: IndexCoordinator,
        embedding_fingerprint: str,
        chunker_version: str,
        config_fingerprint: str,
        embedding_text_max_tokens: int = 384,
        index_heading_max_depth: int = 2,
        index_heading_max_characters: int = 96,
    ) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store transaction, index coordinator, and reproducibility fingerprints.
        """

        # 中文：变量 `_sessions` 用于保存“`sessions`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Session factory reads active metadata and commits publication
        #   transitions.
        self._sessions = sessions
        # 中文：变量 `_coordinator` 用于保存“协调器”相关数据；其精确定义与约束见下方英文说明。
        # English: Coordinator owns staging artifacts and reload validation.
        self._coordinator = coordinator
        # 中文：变量 `_embedding_fingerprint` 用于保存“向量嵌入指纹”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Embedding fingerprint is included in every plan and manifest.
        self._embedding_fingerprint = embedding_fingerprint
        # 中文：变量 `_chunker_version` 用于保存“切块器版本”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Chunker version identifies the chunk population.
        self._chunker_version = chunker_version
        # 中文：变量 `_config_fingerprint` 用于保存“配置指纹”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Complete settings fingerprint identifies the experiment configuration.
        self._config_fingerprint = config_fingerprint
        # 中文：以下关键变量冻结索引文本策略预算，保证任务重建结果可复现。
        # English: These key variables freeze index-text budgets for reproducible rebuilds.
        self._embedding_text_max_tokens = embedding_text_max_tokens
        self._index_heading_max_depth = index_heading_max_depth
        self._index_heading_max_characters = index_heading_max_characters

    def publish_ingested_version(
        self,
        tenant_id: str,
        document_id: str,
        document_version_id: str,
        job_id: str,
        fence: JobFence,
    ) -> IndexBuildResult:
        """中文：该函数或方法负责“发布已接入的版本”相关处理。

        English: Index active content plus one processing version and atomically activate all
        states.
        """

        if fence.tenant_id != tenant_id or fence.job_id != job_id:
            raise ValueError("publication fence does not match the requested job scope")
        # 中文：变量 `index_version_id` 用于保存“索引版本标识符”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: New random version prevents in-place modification of an existing
        #   snapshot.
        index_version_id = new_id("idx")
        with transactional_session(self._sessions) as session:
            repositories = SQLAlchemyRepositories(session)
            # 中文：变量 `active_chunks` 用于保存“活动文本块”相关数据；
            # 其精确定义与约束见下方英文说明。
            # English: Existing active chunks exclude pending-delete and failed documents.
            active_chunks = tuple(repositories.list_active_chunks(tenant_id))
            active_index = repositories.get_active_index(tenant_id)
            expected_active_index_id = active_index.id if active_index is not None else None
            # 中文：变量 `new_chunks` 用于保存“`new`文本块”相关数据；
            # 其精确定义与约束见下方英文说明。
            # English: New processing chunks were persisted before this build began.
            new_chunks = tuple(repositories.list_version_chunks(tenant_id, document_version_id))
            # 中文：变量 `combined_chunks` 用于保存“`combined`文本块”相关数据；
            # 其精确定义与约束见下方英文说明。
            # English: Prior active version of the same logical document is replaced in
            #   the plan.
            combined_chunks = (
                tuple(chunk for chunk in active_chunks if chunk.document_id != document_id)
                + new_chunks
            )
            sources = tuple(repositories.list_sources(tenant_id))
            plan = IndexBuildPlan.from_domain(
                index_version_id=index_version_id,
                tenant_id=tenant_id,
                chunks=combined_chunks,
                sources=sources,
                chunker_version=self._population_chunker_version(combined_chunks),
                embedding_fingerprint=self._embedding_fingerprint,
                config_fingerprint=self._config_fingerprint,
                embedding_text_max_tokens=self._embedding_text_max_tokens,
                max_heading_depth=self._index_heading_max_depth,
                max_heading_characters=self._index_heading_max_characters,
            )
            repositories.add_index(
                IndexVersion(
                    id=index_version_id,
                    tenant_id=tenant_id,
                    status=IndexStatus.STAGING,
                    storage_key=index_version_id,
                    chunk_count=len(plan.entries),
                    config_fingerprint=self._config_fingerprint,
                )
            )

        def activate(version_id: str) -> str | None:
            """中文：该函数或方法负责“激活”相关处理。

            English: Atomically activate index, document version, and durable job success.
            """

            with transactional_session(self._sessions) as session:
                repositories = SQLAlchemyRepositories(session)
                # 中文：关键变量 `activation_time` 让 fencing、索引 CAS 和终态共享同一时刻。
                # English: Key variable `activation_time` gives fencing, index CAS, and the
                # terminal transition one consistent timestamp.
                activation_time = datetime.now(UTC)
                repositories.assert_job_fence(fence, activation_time)
                repositories.set_index_status(tenant_id, version_id, IndexStatus.READY)
                previous = repositories.activate_index(
                    tenant_id,
                    version_id,
                    expected_active_index_id,
                )
                repositories.set_document_status(
                    tenant_id,
                    document_id,
                    DocumentStatus.READY,
                    active_version_id=document_version_id,
                    expected_generation=fence.document_generation,
                )
                repositories.mark_job_succeeded(fence, activation_time)
                return previous

        try:
            previous_id = self._coordinator.build_and_publish(plan, activate)
        except Exception as exc:
            # 中文：本步骤涉及失败的、快照、元数据，具体约束见下方英文说明。
            # English: Failed snapshot metadata is retained for diagnosis and recovery
            #   tooling.
            with transactional_session(self._sessions) as session:
                # 中文：生命周期或所有权失效属于取消，不应伪装成索引实现故障。
                # English: Lifecycle/ownership invalidation is cancellation, not an index fault.
                terminal_status = (
                    IndexStatus.CANCELLED
                    if isinstance(
                        exc,
                        (JobCancelledError, LeaseLostError, LifecycleFenceError),
                    )
                    else IndexStatus.FAILED
                )
                SQLAlchemyRepositories(session).set_index_status(
                    tenant_id,
                    index_version_id,
                    terminal_status,
                    error_code=(
                        exc.detail.code if hasattr(exc, "detail") else "INDEX_PUBLICATION_FAILED"
                    ),
                    error_message="The candidate index could not be published.",
                )
            raise
        return IndexBuildResult(
            index_version_id=index_version_id,
            chunk_count=len(plan.entries),
            activated=True,
            previous_index_version_id=previous_id,
        )

    def rebuild_active(self, tenant_id: str, *, allow_empty: bool = False) -> IndexBuildResult:
        """中文：该函数或方法负责“重建活动”相关处理。

        English: Build and activate a fresh snapshot from current READY documents only.

        中文：管理员手动重建默认禁止空索引；删除流程可显式允许空快照以撤销旧内容。
        English: Manual rebuilds reject empty indexes by default; deletion may explicitly allow
        an empty snapshot to revoke old content.
        """

        # 中文：变量 `index_version_id` 用于保存“索引版本标识符”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Fresh immutable version identifies this manual or delete-triggered
        #   rebuild.
        index_version_id = new_id("idx")
        with transactional_session(self._sessions) as session:
            repositories = SQLAlchemyRepositories(session)
            active_chunks = tuple(repositories.list_active_chunks(tenant_id))
            if not active_chunks and not allow_empty:
                raise ValidationError(
                    error_detail(
                        "EMPTY_INDEX_REBUILD_BLOCKED",
                        ErrorCategory.VALIDATION,
                        "No READY document chunks are available; the active index was unchanged.",
                    )
                )
            active_index = repositories.get_active_index(tenant_id)
            expected_active_index_id = active_index.id if active_index is not None else None
            sources = tuple(repositories.list_sources(tenant_id))
            plan = IndexBuildPlan.from_domain(
                index_version_id,
                tenant_id,
                active_chunks,
                sources,
                self._population_chunker_version(active_chunks),
                self._embedding_fingerprint,
                self._config_fingerprint,
                self._embedding_text_max_tokens,
                self._index_heading_max_depth,
                self._index_heading_max_characters,
            )
            repositories.add_index(
                IndexVersion(
                    id=index_version_id,
                    tenant_id=tenant_id,
                    status=IndexStatus.STAGING,
                    storage_key=index_version_id,
                    chunk_count=len(plan.entries),
                    config_fingerprint=self._config_fingerprint,
                )
            )

        def activate(version_id: str) -> str | None:
            """中文：该函数或方法负责“激活”相关处理。

            English: Atomically mark the fully validated snapshot ready and active.
            """

            with transactional_session(self._sessions) as session:
                repositories = SQLAlchemyRepositories(session)
                repositories.set_index_status(tenant_id, version_id, IndexStatus.READY)
                return repositories.activate_index(
                    tenant_id,
                    version_id,
                    expected_active_index_id,
                )

        try:
            previous_id = self._coordinator.build_and_publish(plan, activate)
        except Exception as exc:
            # 中文：手动重建、删除重建与接入发布使用相同失败终态，杜绝永久 STAGING。
            # English: Manual/delete/ingestion publication share one terminal failure outcome.
            with transactional_session(self._sessions) as session:
                SQLAlchemyRepositories(session).set_index_status(
                    tenant_id,
                    index_version_id,
                    IndexStatus.FAILED,
                    error_code=(
                        exc.detail.code if hasattr(exc, "detail") else "INDEX_PUBLICATION_FAILED"
                    ),
                    error_message="The candidate index could not be published.",
                )
            raise
        return IndexBuildResult(
            index_version_id=index_version_id,
            chunk_count=len(plan.entries),
            activated=True,
            previous_index_version_id=previous_id,
        )

    def _population_chunker_version(self, chunks: tuple[Chunk, ...]) -> str:
        """中文：汇总混合索引中每个 Chunk 的真实策略版本，替代含糊的全局标签。

        English: Summarize actual per-chunk strategy versions in a mixed index instead of a
        vague global label.
        """

        versions = sorted({chunk.chunker_version for chunk in chunks if chunk.chunker_version})
        return "+".join(versions) if versions else self._chunker_version


class KnowledgeService:
    """中文：该类用于表示或实现“知识服务（KnowledgeService）”的职责。

    English: Expose permission-aware document details and two-phase document deletion.
    """

    def __init__(
        self,
        sessions: sessionmaker[Session],
        rebuild_index: Callable[[str], IndexBuildResult],
        strategy_registry: ChunkStrategyRegistry | None = None,
        cleanup_files: Callable[[str, tuple[str, ...]], None] | None = None,
    ) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store metadata transactions and the formal index rebuild use case.
        """

        # 中文：变量 `_sessions` 用于保存“`sessions`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Session factory owns each lifecycle transaction.
        self._sessions = sessions
        # 中文：变量 `_rebuild_index` 用于保存“重建索引”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Rebuild callback excludes PENDING_DELETE content through repository
        #   queries.
        self._rebuild_index = rebuild_index
        # 中文：变量 `_strategy_registry` 在管理员保存覆盖值时立即执行合法性校验。
        # English: `_strategy_registry` validates administrator overrides when they are saved.
        self._strategy_registry = strategy_registry
        # 中文：物理文件清理在新索引发布后、删除终态提交前执行。
        # English: Physical file cleanup runs after new-index publication and before terminal
        # deletion commit.
        self._cleanup_files = cleanup_files

    def document_detail(self, user: UserContext, document_id: str) -> DocumentDetail:
        """中文：该函数或方法负责“文档详情”相关处理。

        English: Return one tenant-owned document without disclosing cross-tenant existence.
        """

        with transactional_session(self._sessions) as session:
            document = SQLAlchemyRepositories(session).get_document(
                user.tenant_id,
                document_id,
            )
            if document is None:
                raise NotFoundError(
                    error_detail(
                        "DOCUMENT_NOT_FOUND",
                        ErrorCategory.NOT_FOUND,
                        "The document does not exist.",
                    )
                )
            if not user.is_admin() and document.source_id not in user.allowed_source_ids:
                raise NotFoundError(
                    error_detail(
                        "DOCUMENT_NOT_FOUND",
                        ErrorCategory.NOT_FOUND,
                        "The document does not exist.",
                    )
                )
            active_version = (
                SQLAlchemyRepositories(session).get_version(
                    user.tenant_id,
                    document.active_version_id,
                )
                if document.active_version_id is not None
                else None
            )
            return DocumentDetail(
                document_id=document.id,
                source_id=document.source_id,
                title=document.title,
                status=document.status.value,
                active_version_id=document.active_version_id,
                content_profile=(
                    active_version.content_profile.value if active_version is not None else None
                ),
                chunk_strategy_version=(
                    active_version.chunk_strategy_version if active_version is not None else None
                ),
                quality_metrics=(
                    active_version.quality_metrics if active_version is not None else {}
                ),
            )

    def list_sources(self, user: UserContext) -> tuple[dict[str, object], ...]:
        """中文：该函数或方法负责“列出资料源”相关处理。

        English: Return active sources visible to the trusted user context.
        """

        with transactional_session(self._sessions) as session:
            sources = SQLAlchemyRepositories(session).list_sources(user.tenant_id)
            return tuple(
                {
                    "source_id": source.id,
                    "name": source.name,
                    "description": source.description,
                    "content_profile": source.content_profile.value,
                    "chunk_strategy_override": source.chunk_strategy_override,
                    "visibility": source.visibility.value,
                }
                for source in sources
                if user.is_admin()
                or source.visibility.value == "tenant"
                or source.id in user.allowed_source_ids
                or bool(source.allowed_group_ids & user.group_ids)
            )

    def update_source_content_profile(
        self,
        user: UserContext,
        source_id: str,
        content_profile: ContentProfile,
        chunk_strategy_override: str | None = None,
    ) -> dict[str, object]:
        """中文：允许租户管理员更新资料源画像，并提示后续需要重新处理文档。

        English: Let tenant administrators update a source profile and flag reprocessing need.
        """

        if not user.is_admin():
            raise PermissionDeniedError(
                error_detail(
                    "SOURCE_PROFILE_ADMIN_DENIED",
                    ErrorCategory.PERMISSION,
                    "Only tenant administrators may update source content profiles.",
                )
            )
        if self._strategy_registry is not None:
            try:
                self._strategy_registry.resolve(content_profile, chunk_strategy_override)
            except ValueError as exc:
                raise ValidationError(
                    error_detail(
                        "INVALID_CHUNK_STRATEGY",
                        ErrorCategory.VALIDATION,
                        "The requested chunk strategy override is not registered.",
                    )
                ) from exc
        with transactional_session(self._sessions) as session:
            repositories = SQLAlchemyRepositories(session)
            current_source = repositories.get_source(user.tenant_id, source_id)
            if current_source is None:
                raise NotFoundError(
                    error_detail(
                        "SOURCE_NOT_FOUND",
                        ErrorCategory.NOT_FOUND,
                        "The source does not exist.",
                    )
                )
            # 中文：只有画像或策略实际变化时才要求重新处理，避免无效警告。
            # English: Reprocessing is required only when the profile or strategy actually changes.
            changed = (
                current_source.content_profile is not content_profile
                or current_source.chunk_strategy_override != chunk_strategy_override
            )
            source = repositories.update_source_content_profile(
                user.tenant_id,
                source_id,
                content_profile,
                chunk_strategy_override,
            )
            if source is None:
                raise NotFoundError(
                    error_detail(
                        "SOURCE_NOT_FOUND",
                        ErrorCategory.NOT_FOUND,
                        "The source does not exist.",
                    )
                )
            return {
                "source_id": source.id,
                "name": source.name,
                "description": source.description,
                "content_profile": source.content_profile.value,
                "chunk_strategy_override": source.chunk_strategy_override,
                "visibility": source.visibility.value,
                "requires_reprocessing": changed,
            }

    def list_indexes(self, user: UserContext) -> tuple[dict[str, object], ...]:
        """中文：该函数或方法负责“列出索引”相关处理。

        English: Return tenant index versions to administrators.
        """

        if not user.is_admin():
            raise PermissionDeniedError(
                error_detail(
                    "INDEX_ADMIN_DENIED",
                    ErrorCategory.PERMISSION,
                    "Only tenant administrators may inspect index versions.",
                )
            )
        with transactional_session(self._sessions) as session:
            indexes = SQLAlchemyRepositories(session).list_indexes(user.tenant_id)
            return tuple(
                {
                    "index_version_id": index.id,
                    "status": index.status.value,
                    "chunk_count": index.chunk_count,
                    "config_fingerprint": index.config_fingerprint,
                    "created_at": index.created_at.isoformat(),
                    "activated_at": (
                        index.activated_at.isoformat() if index.activated_at else None
                    ),
                }
                for index in indexes
            )

    def delete_document(
        self,
        user: UserContext,
        document_id: str,
        idempotency_key: str | None = None,
    ) -> DeletionAccepted:
        """中文：立即撤销可检索性并持久化异步删除任务。

        English: Revoke retrieval immediately and persist an asynchronous deletion job.
        """

        if not user.is_admin():
            raise PermissionDeniedError(
                error_detail(
                    "DOCUMENT_DELETE_DENIED",
                    ErrorCategory.PERMISSION,
                    "Only tenant administrators may delete documents.",
                )
            )
        with transactional_session(self._sessions) as session:
            repositories = SQLAlchemyRepositories(session)
            existing = repositories.get_job_by_idempotency(
                user.tenant_id,
                JobType.DELETION,
                idempotency_key,
            )
            if existing is not None:
                return DeletionAccepted(existing.id, existing.document_id, "pending_delete")
            document = repositories.get_document(user.tenant_id, document_id)
            if document is None:
                raise NotFoundError(
                    error_detail(
                        "DOCUMENT_NOT_FOUND",
                        ErrorCategory.NOT_FOUND,
                        "The document does not exist.",
                    )
                )
            if document.status in {DocumentStatus.PENDING_DELETE, DocumentStatus.DELETED}:
                latest = repositories.get_latest_document_job(
                    user.tenant_id,
                    document_id,
                    JobType.DELETION,
                )
                if latest is not None:
                    return DeletionAccepted(latest.id, document_id, document.status.value)
            versions = tuple(repositories.list_document_versions(user.tenant_id, document_id))
            if not versions:
                raise ValidationError(
                    error_detail(
                        "DOCUMENT_VERSION_NOT_FOUND",
                        ErrorCategory.VALIDATION,
                        "The document has no immutable version to delete.",
                    )
                )
            # 中文：单次事务递增 generation 并取消旧任务；此后旧 Worker 无权写入。
            # English: One transaction increments generation and cancels jobs; stale workers stop.
            deleting = repositories.request_document_deletion(
                user.tenant_id,
                document_id,
                datetime.now(UTC),
            )
            if deleting is None:
                raise NotFoundError(
                    error_detail(
                        "DOCUMENT_NOT_FOUND",
                        ErrorCategory.NOT_FOUND,
                        "The document does not exist.",
                    )
                )
            repositories.record_revocation(
                user.tenant_id,
                RevocationScopeType.DOCUMENT,
                document_id,
                "DOCUMENT_DELETE_REQUESTED",
                user.user_id,
                datetime.now(UTC),
            )
            deletion_job_id = new_id("job")
            repositories.add_job(
                IngestionJob(
                    id=deletion_job_id,
                    tenant_id=user.tenant_id,
                    document_id=document_id,
                    # 中文：删除任务绑定最新版本仅用于外键和审计，不解析其正文。
                    # English: Deletion binds the latest version for FK/audit only; it never parses
                    # its content.
                    document_version_id=versions[-1].id,
                    document_generation_snapshot=deleting.lifecycle_generation,
                    status=JobStatus.PENDING,
                    idempotency_key=idempotency_key,
                    job_type=JobType.DELETION,
                )
            )
        return DeletionAccepted(deletion_job_id, document_id, DocumentStatus.PENDING_DELETE.value)

    def process_deletion_job(self, job: IngestionJob, fence: JobFence) -> None:
        """中文：发布不含目标文档的索引，清理文件，再以相同 fence 提交终态。

        English: Publish an index without the document, clean files, then commit terminal state
        with the same fence.
        """

        if job.job_type is not JobType.DELETION:
            raise ValueError("deletion processor received a non-deletion job")
        self._rebuild_index(job.tenant_id)
        with transactional_session(self._sessions) as session:
            versions = tuple(
                SQLAlchemyRepositories(session).list_document_versions(
                    job.tenant_id,
                    job.document_id,
                )
            )
        if self._cleanup_files is not None:
            self._cleanup_files(
                job.tenant_id,
                tuple(version.storage_key for version in versions),
            )
        terminal_time = datetime.now(UTC)
        with transactional_session(self._sessions) as session:
            repositories = SQLAlchemyRepositories(session)
            # 中文：两个终态写入共享一个数据库事务；先 CAS 任务再完成文档。
            # English: Both terminal writes share one transaction; CAS the job before completing
            # the document.
            repositories.mark_job_succeeded(fence, terminal_time)
            repositories.complete_document_deletion(
                job.tenant_id,
                job.document_id,
                fence.document_generation,
                terminal_time,
            )

    def job_detail(self, user: UserContext, job_id: str) -> JobDetail:
        """中文：仅向租户管理员返回经脱敏的任务详情。

        English: Return redacted job details only to a tenant administrator.
        """

        if not user.is_admin():
            raise PermissionDeniedError(
                error_detail(
                    "JOB_DETAIL_DENIED",
                    ErrorCategory.PERMISSION,
                    "Only tenant administrators may inspect background jobs.",
                )
            )
        with transactional_session(self._sessions) as session:
            job = SQLAlchemyRepositories(session).get_job(user.tenant_id, job_id)
            if job is None:
                raise NotFoundError(
                    error_detail(
                        "JOB_NOT_FOUND",
                        ErrorCategory.NOT_FOUND,
                        "The background job does not exist.",
                    )
                )
        return JobDetail(
            job_id=job.id,
            job_type=job.job_type.value,
            document_id=job.document_id,
            document_version_id=job.document_version_id,
            status=job.status.value,
            attempt_count=job.attempt_count,
            error_code=job.error_code,
            error_message=job.error_message,
        )
