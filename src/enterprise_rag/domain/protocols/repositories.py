"""中文：本模块负责实现“仓储”相关功能。

English: Define tenant-scoped persistence ports for domain entities and durable jobs.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from enterprise_rag.core.enums import DocumentStatus, JobStatus
from enterprise_rag.domain.models import (
    Chunk,
    Document,
    DocumentVersion,
    IndexVersion,
    IngestionJob,
    JobFence,
    Source,
    TraceRecord,
)


class SourceRepository(Protocol):
    """中文：该类用于表示或实现“资料源仓储（SourceRepository）”的职责。

    English: Persist and query routable knowledge sources.
    """

    def add(self, source: Source) -> None:
        """中文：该函数或方法负责“新增目标对象”相关处理。

        English: Persist a new source.
        """

    def get(self, tenant_id: str, source_id: str) -> Source | None:
        """中文：该函数或方法负责“读取目标对象”相关处理。

        English: Return a source only when it belongs to the tenant.
        """

    def list_authorized(self, tenant_id: str, source_ids: frozenset[str]) -> Sequence[Source]:
        """中文：该函数或方法负责“列出已授权”相关处理。

        English: Return active sources intersected with an authorized source set.
        """


class DocumentRepository(Protocol):
    """中文：该类用于表示或实现“文档仓储（DocumentRepository）”的职责。

    English: Persist logical documents and immutable document versions.
    """

    def add_document(self, document: Document) -> None:
        """中文：该函数或方法负责“新增文档”相关处理。

        English: Persist a new logical document.
        """

    def add_version(self, version: DocumentVersion) -> None:
        """中文：该函数或方法负责“新增版本”相关处理。

        English: Persist a new immutable document version.
        """

    def get_document(self, tenant_id: str, document_id: str) -> Document | None:
        """中文：该函数或方法负责“获取文档”相关处理。

        English: Return a logical document only when it belongs to the tenant.
        """

    def get_version(self, tenant_id: str, version_id: str) -> DocumentVersion | None:
        """中文：该函数或方法负责“获取版本”相关处理。

        English: Return an immutable version only when it belongs to the tenant.
        """

    def set_status(
        self,
        tenant_id: str,
        document_id: str,
        status: DocumentStatus,
        active_version_id: str | None = None,
    ) -> None:
        """中文：该函数或方法负责“设置状态”相关处理。

        English: Update lifecycle state and optionally activate an immutable version.
        """

    def list_active_versions(self, tenant_id: str) -> Sequence[DocumentVersion]:
        """中文：该函数或方法负责“列出活动版本”相关处理。

        English: Return versions whose logical documents are ready and active.
        """


class ChunkRepository(Protocol):
    """中文：该类用于表示或实现“文本块仓储（ChunkRepository）”的职责。

    English: Persist deterministic chunks and retrieve authorized active content.
    """

    def replace_version_chunks(
        self,
        tenant_id: str,
        document_version_id: str,
        chunks: Sequence[Chunk],
    ) -> None:
        """中文：该函数或方法负责“`replace`版本文本块”相关处理。

        English: Atomically replace chunks for one not-yet-active document version.
        """

    def list_active(self, tenant_id: str) -> Sequence[Chunk]:
        """中文：该函数或方法负责“列出活动”相关处理。

        English: Return chunks belonging to currently active document versions.
        """

    def get_many(
        self,
        tenant_id: str,
        chunk_ids: Sequence[str],
    ) -> Sequence[Chunk]:
        """中文：按安全默认语义返回当前可在线检索的 Chunk。

        English: Return currently retrievable chunks with secure-by-default semantics.
        """

    def get_retrievable(
        self,
        tenant_id: str,
        chunk_ids: Sequence[str],
    ) -> Sequence[Chunk]:
        """中文：返回当前允许进入在线问答与引用流程的活动 Chunk。

        English: Return active chunks currently eligible for online answers and citations.
        """

    def replace_version_chunks_fenced(
        self,
        fence: JobFence,
        document_version_id: str,
        chunks: Sequence[Chunk],
        now: datetime,
    ) -> None:
        """中文：只允许有效 Worker 代次替换候选版本 Chunk。

        English: Replace candidate-version chunks only for a live worker generation.
        """

    def update_version_quality_metrics_fenced(
        self,
        fence: JobFence,
        document_version_id: str,
        metrics: dict[str, object],
        warnings: tuple[str, ...],
        now: datetime,
    ) -> None:
        """中文：只允许有效 Worker 代次写入质量门审计结果。

        English: Store quality-gate audit results only for a live worker generation.
        """


class IngestionJobRepository(Protocol):
    """中文：该类用于表示或实现“资料接入任务仓储（IngestionJobRepository）”的职责。

    English: Persist, lease, complete, and recover durable ingestion jobs.
    """

    def add(self, job: IngestionJob) -> None:
        """中文：该函数或方法负责“新增目标对象”相关处理。

        English: Persist a new pending job.
        """

    def get(self, tenant_id: str, job_id: str) -> IngestionJob | None:
        """中文：该函数或方法负责“读取目标对象”相关处理。

        English: Return a job only when it belongs to the tenant.
        """

    def claim_next(
        self,
        worker_id: str,
        now: datetime,
        lease_until: datetime,
    ) -> IngestionJob | None:
        """中文：该函数或方法负责“领取下一个”相关处理。

        English: Atomically claim the next pending or expired job.
        """

    def renew_lease(
        self,
        fence: JobFence,
        now: datetime,
        lease_until: datetime,
    ) -> bool:
        """中文：为仍由相同 Worker 代次持有的任务续租。

        English: Renew a job still held by the same worker generation.
        """

    def assert_fence(self, fence: JobFence, now: datetime) -> None:
        """中文：在提交任务副作用前验证 fencing token。

        English: Verify a fencing token before committing job side effects.
        """

    def mark_succeeded(self, fence: JobFence, now: datetime) -> None:
        """中文：该函数或方法负责“标记成功的”相关处理。

        English: Mark a leased job as successfully completed.
        """

    def mark_failed(
        self,
        fence: JobFence,
        now: datetime,
        error_code: str,
        error_message: str,
    ) -> None:
        """中文：该函数或方法负责“标记失败的”相关处理。

        English: Mark a leased job as failed with safe diagnostics.
        """

    def mark_attention_required(
        self,
        fence: JobFence,
        now: datetime,
        status: JobStatus,
        error_code: str,
        error_message: str,
    ) -> None:
        """中文：将有效租约任务置为 OCR、复核或不支持终态。

        English: Move a live leased job to an OCR, review, or unsupported terminal state.
        """


class IndexRepository(Protocol):
    """中文：该类用于表示或实现“索引仓储（IndexRepository）”的职责。

    English: Persist immutable index metadata and transactionally switch active versions.
    """

    def add(self, index: IndexVersion) -> None:
        """中文：该函数或方法负责“新增目标对象”相关处理。

        English: Persist a newly staged index version.
        """

    def get_active(self, tenant_id: str) -> IndexVersion | None:
        """中文：该函数或方法负责“获取活动”相关处理。

        English: Return the tenant's currently active index snapshot.
        """

    def activate(
        self,
        tenant_id: str,
        index_version_id: str,
        expected_active_index_id: str | None,
    ) -> str | None:
        """中文：该函数或方法负责“激活”相关处理。

        English: Activate a ready snapshot only if the expected active version still matches.
        """

    def list_versions(self, tenant_id: str) -> Sequence[IndexVersion]:
        """中文：该函数或方法负责“列出版本”相关处理。

        English: Return tenant index versions from newest to oldest.
        """


class TraceRepository(Protocol):
    """中文：该类用于表示或实现“追踪仓储（TraceRepository）”的职责。

    English: Persist and retrieve redacted trace summaries.
    """

    def add(self, trace: TraceRecord) -> None:
        """中文：该函数或方法负责“新增目标对象”相关处理。

        English: Persist a new trace summary.
        """

    def get(self, tenant_id: str, trace_id: str) -> TraceRecord | None:
        """中文：该函数或方法负责“读取目标对象”相关处理。

        English: Return a trace only when it belongs to the tenant.
        """
