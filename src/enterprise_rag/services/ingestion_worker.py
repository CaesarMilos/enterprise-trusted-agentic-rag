"""中文：本模块负责实现“资料接入工作进程”相关功能。

English: Lease durable ingestion jobs, prepare chunks, and publish indexes without losing old
service.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from enterprise_rag.core.enums import DocumentStatus, JobStatus
from enterprise_rag.core.exceptions import (
    EnterpriseRAGError,
    JobCancelledError,
    LeaseLostError,
    LifecycleFenceError,
)
from enterprise_rag.domain.models import JobFence, job_fence_from_job
from enterprise_rag.domain.protocols.storage import FileStore
from enterprise_rag.infrastructure.persistence.database import transactional_session
from enterprise_rag.infrastructure.persistence.repositories import SQLAlchemyRepositories
from enterprise_rag.ingestion.pipeline import IngestionPipeline
from enterprise_rag.ingestion.semantic_chunker import ChunkingContext
from enterprise_rag.services.job_lease_guard import JobLeaseGuard


class IngestionWorker:
    """中文：该类用于表示或实现“资料接入工作进程（IngestionWorker）”的职责。

    English: Process one recoverable SQLite-backed job per polling iteration.
    """

    def __init__(
        self,
        sessions: sessionmaker[Session],
        file_store: FileStore,
        pipeline: IngestionPipeline,
        publish_index: Callable[[str, str, str, str, JobFence], object],
        worker_id: str,
        lease_seconds: int,
        heartbeat_seconds: int,
    ) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store durable job, parsing, and transactional publication dependencies.
        """

        # 中文：变量 `_sessions` 用于保存“`sessions`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Session factory owns short explicit transactions.
        self._sessions = sessions
        # 中文：变量 `_file_store` 用于保存“文件存储”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Original-file store supplies a safe local parser path.
        self._file_store = file_store
        # 中文：变量 `_pipeline` 用于保存“流水线”相关数据；其精确定义与约束见下方英文说明。
        # English: Deterministic ingestion pipeline produces immutable chunks.
        self._pipeline = pipeline
        # 中文：变量 `_publish_index` 用于保存“`publish`索引”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Publication callback must atomically activate index, document version,
        #   and job success.
        self._publish_index = publish_index
        # 中文：变量 `_worker_id` 用于保存“工作进程标识符”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Stable process identity owns leases.
        self._worker_id = worker_id
        # 中文：变量 `_lease_seconds` 用于保存“`lease``seconds`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Lease duration allows recovery after process death.
        self._lease_seconds = lease_seconds
        # 中文：关键变量 `_heartbeat_seconds` 控制长任务的主动续租间隔。
        # English: Key variable `_heartbeat_seconds` controls active renewal for long jobs.
        self._heartbeat_seconds = heartbeat_seconds

    def run_once(self) -> bool:
        """中文：该函数或方法负责“执行一轮处理”相关处理。

        English: Claim and process one job; return false when no work is available.
        """

        # 中文：变量 `now` 用于保存“`now`”相关数据；其精确定义与约束见下方英文说明。
        # English: Claim transaction commits before expensive parsing starts.
        now = datetime.now(UTC)
        with transactional_session(self._sessions) as session:
            repositories = SQLAlchemyRepositories(session)
            job = repositories.claim_next_job(
                self._worker_id,
                now,
                now + timedelta(seconds=self._lease_seconds),
            )
            if job is None:
                return False
            # 中文：关键变量 `fence` 固定本轮领取的 Worker 和 attempt generation。
            # English: Key variable `fence` pins this claim's worker and attempt generation.
            fence = job_fence_from_job(job)
            # 中文：变量 `version` 用于保存“版本”相关数据；其精确定义与约束见下方英文说明。
            # English: Version metadata and document status are captured under the same
            #   tenant scope.
            version = repositories.get_version(job.tenant_id, job.document_version_id)
            if version is None:
                repositories.mark_job_failed(
                    fence,
                    datetime.now(UTC),
                    "DOCUMENT_VERSION_NOT_FOUND",
                    "The document version no longer exists.",
                )
                return True
            # 中文：逻辑文档用于判断候选版本失败时是否应继续保持旧版本 READY。
            # English: The logical document determines whether an old active version remains READY.
            document = repositories.get_document(job.tenant_id, job.document_id)
            if document is None:
                repositories.mark_job_failed(
                    fence,
                    datetime.now(UTC),
                    "DOCUMENT_NOT_FOUND",
                    "The logical document no longer exists.",
                )
                return True
            # 中文：领取租约后立即验证文档 generation；删除竞态在昂贵解析前终止。
            # English: Validate document generation after claim so deletion stops before parsing.
            repositories.assert_job_fence(fence, datetime.now(UTC))
            # 中文：关键变量 `has_active_version` 冻结失败恢复语义，候选任务不影响旧服务。
            # English: Key variable `has_active_version` freezes failure semantics so a candidate
            # cannot interrupt old service.
            has_active_version = document.active_version_id is not None
            if not has_active_version:
                repositories.set_document_status(
                    job.tenant_id,
                    job.document_id,
                    DocumentStatus.PROCESSING,
                    expected_generation=fence.document_generation,
                )
        try:
            # 中文：关键变量 `lease_guard` 在 OCR、Embedding 和索引构建期间持续续租。
            # English: Key variable `lease_guard` renews through OCR, embedding, and indexing.
            lease_guard = JobLeaseGuard(
                self._sessions,
                fence,
                self._lease_seconds,
                self._heartbeat_seconds,
            )
            with lease_guard:
                # 中文：变量 `original_path` 是由可信文件存储适配器解析的安全本地路径。
                # English: `original_path` is a safe local path resolved by the trusted store.
                original_path = self._file_store.materialized_path(
                    version.tenant_id,
                    version.storage_key,
                )
                prepared = self._pipeline.prepare(
                    original_path,
                    version.original_filename,
                    version.media_type,
                    ChunkingContext(
                        tenant_id=version.tenant_id,
                        source_id=version.source_id,
                        document_id=version.document_id,
                        document_version_id=version.id,
                    ),
                    content_profile=version.content_profile,
                    strategy_override=version.chunk_strategy_id,
                    expected_strategy_version=version.chunk_strategy_version,
                    expected_chunk_parameters=version.chunk_parameters,
                    expected_embedding_fingerprint=version.embedding_fingerprint,
                    expected_boundary_model_fingerprint=version.boundary_model_fingerprint,
                )
                lease_guard.checkpoint()
                # 中文：Chunk 和质量指标在一个短事务内通过相同 fencing token 提交。
                # English: Chunks and quality metrics commit in one short fenced transaction.
                persistence_time = datetime.now(UTC)
                with transactional_session(self._sessions) as session:
                    repositories = SQLAlchemyRepositories(session)
                    repositories.replace_version_chunks_fenced(
                        fence,
                        version.id,
                        prepared.chunks,
                        persistence_time,
                    )
                    repositories.update_version_quality_metrics_fenced(
                        fence,
                        version.id,
                        dict(prepared.quality_assessment.metrics),
                        prepared.quality_assessment.warnings,
                        persistence_time,
                    )
                lease_guard.checkpoint()
                # 中文：发布回调携带 fencing token，并在最终激活事务中再次验证。
                # English: Publication carries the fence and revalidates it at activation.
                self._publish_index(
                    version.tenant_id,
                    version.document_id,
                    version.id,
                    job.id,
                    fence,
                )
        except JobCancelledError:
            # 中文：取消只收口任务，不得把删除中的文档改为 FAILED。
            # English: Cancellation closes only the job and never marks a deleting document failed.
            try:
                with transactional_session(self._sessions) as session:
                    SQLAlchemyRepositories(session).mark_job_cancelled(
                        fence,
                        datetime.now(UTC),
                        "lifecycle_cancelled",
                    )
            except (LeaseLostError, LifecycleFenceError, JobCancelledError):
                pass
            return True
        except (LeaseLostError, LifecycleFenceError):
            # 中文：失租是所有权转移而非任务失败；旧 Worker 不得再写任何终态。
            # English: Lease loss transfers ownership; the old worker must write no terminal state.
            return True
        except Exception as exc:
            # 中文：变量 `error_code` 用于保存“错误`code`”相关数据；
            # 其精确定义与约束见下方英文说明。
            # English: Old ACTIVE index remains untouched; failure is made durable and
            #   visible.
            error_code = (
                exc.detail.code if isinstance(exc, EnterpriseRAGError) else "INGESTION_FAILED"
            )
            error_message = (
                exc.detail.message
                if isinstance(exc, EnterpriseRAGError)
                else "The document could not be ingested."
            )
            try:
                with transactional_session(self._sessions) as session:
                    repositories = SQLAlchemyRepositories(session)
                    # 中文：OCR、人工复核和明确不支持属于安全产品状态，不归类为程序失败。
                    # English: OCR, review, and unsupported inputs are safe product states,
                    # not code failures.
                    attention_states = {
                        "PDF_OCR_REQUIRED": (JobStatus.NEEDS_OCR, DocumentStatus.NEEDS_OCR),
                        "DOCUMENT_NEEDS_REVIEW": (
                            JobStatus.NEEDS_REVIEW,
                            DocumentStatus.NEEDS_REVIEW,
                        ),
                        "PDF_UNSUPPORTED": (JobStatus.UNSUPPORTED, DocumentStatus.UNSUPPORTED),
                    }
                    attention = attention_states.get(error_code)
                    terminal_time = datetime.now(UTC)
                    if attention is None:
                        repositories.mark_job_failed(
                            fence,
                            terminal_time,
                            error_code,
                            error_message,
                        )
                        document_status = DocumentStatus.FAILED
                    else:
                        job_status, document_status = attention
                        repositories.mark_job_attention_required(
                            fence,
                            terminal_time,
                            job_status,
                            error_code,
                            error_message,
                        )
                    if not has_active_version:
                        repositories.set_document_status(
                            job.tenant_id,
                            job.document_id,
                            document_status,
                            expected_generation=fence.document_generation,
                        )
            except (LeaseLostError, LifecycleFenceError, JobCancelledError):
                # 中文：异常处理期间失租同样禁止旧 Worker 覆盖新代次的终态。
                # English: Losing the lease during error handling also forbids stale writes.
                return True
        return True
