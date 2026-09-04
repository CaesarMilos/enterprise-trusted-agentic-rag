"""中文：验证删除 generation、任务取消和 Worker fencing 的数据库竞态边界。

English: Verify database race boundaries for deletion generation, cancellation, and worker fencing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from enterprise_rag.core.enums import DocumentStatus, JobStatus, SourceVisibility
from enterprise_rag.core.exceptions import JobCancelledError
from enterprise_rag.domain.models import (
    Document,
    DocumentVersion,
    IngestionJob,
    Source,
    job_fence_from_job,
)
from enterprise_rag.infrastructure.persistence.database import (
    create_database_engine,
    create_session_factory,
    initialize_database,
    transactional_session,
)
from enterprise_rag.infrastructure.persistence.orm_models import TenantRow
from enterprise_rag.infrastructure.persistence.repositories import SQLAlchemyRepositories


def test_delete_generation_cancels_and_fences_running_job(tmp_path: Path) -> None:
    """中文：删除后即使原 Worker 租约仍有效，也不能再提交 Chunk 或发布 READY。

    English: After deletion, a still-leased worker cannot persist chunks or publish READY.
    """

    database_path = tmp_path / "v4-fencing.db"
    engine = create_database_engine(f"sqlite:///{database_path}")
    initialize_database(engine)
    sessions = create_session_factory(engine)
    with transactional_session(sessions) as session:
        repositories = SQLAlchemyRepositories(session)
        session.add(TenantRow(id="tenant-a", name="Tenant A", is_active=True))
        session.flush()
        repositories.add_source(
            Source(
                "source-a",
                "tenant-a",
                "Manuals",
                "Device manuals",
                visibility=SourceVisibility.TENANT,
            )
        )
        repositories.add_document(Document("document-a", "tenant-a", "source-a", "Manual"))
        repositories.add_version(
            DocumentVersion(
                "version-a",
                "tenant-a",
                "document-a",
                "source-a",
                1,
                "manual.txt",
                "txt",
                "hash-a",
                "storage-a",
                10,
            )
        )
        repositories.add_job(
            IngestionJob(
                "job-a",
                "tenant-a",
                "document-a",
                "version-a",
                document_generation_snapshot=0,
            )
        )
    now = datetime.now(UTC)
    with transactional_session(sessions) as session:
        claimed = SQLAlchemyRepositories(session).claim_next_job(
            "worker-a", now, now + timedelta(minutes=5)
        )
        assert claimed is not None
        fence = job_fence_from_job(claimed)
    with transactional_session(sessions) as session:
        deleting = SQLAlchemyRepositories(session).request_document_deletion(
            "tenant-a", "document-a", datetime.now(UTC)
        )
        assert deleting is not None and deleting.lifecycle_generation == 1
    with transactional_session(sessions) as session:
        repositories = SQLAlchemyRepositories(session)
        with pytest.raises(JobCancelledError):
            repositories.assert_job_fence(fence, datetime.now(UTC))
        repositories.mark_job_cancelled(fence, datetime.now(UTC), "document_deleted")
    with transactional_session(sessions) as session:
        repositories = SQLAlchemyRepositories(session)
        repositories.complete_document_deletion("tenant-a", "document-a", 1, datetime.now(UTC))
        document = repositories.get_document("tenant-a", "document-a")
        job = repositories.get_job("tenant-a", "job-a")
        assert document is not None and document.status is DocumentStatus.DELETED
        assert job is not None and job.status is JobStatus.CANCELLED
