"""中文：验证 V5 任务租约检查的精确结果与终态保护。

English: Verify precise V5 lease-check outcomes and terminal-state protection.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from enterprise_rag.core.enums import (
    DocumentStatus,
    JobStatus,
    LeaseCheckResult,
    SourceVisibility,
)
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


def _seed(tmp_path: Path) -> sessionmaker[Session]:
    """中文：创建一个可领取任务的隔离数据库。

    English: Create an isolated database containing one claimable job.
    """

    engine = create_database_engine(f"sqlite:///{tmp_path / 'lease-outcomes.db'}")
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
        repositories.add_job(IngestionJob("job-a", "tenant-a", "document-a", "version-a"))
    return sessions


def test_lease_check_distinguishes_cancel_expiry_and_new_owner(tmp_path: Path) -> None:
    """中文：取消、过期和新 Worker 接管分别返回稳定枚举值。

    English: Cancellation, expiration, and a new owner produce distinct stable enum values.
    """

    sessions = _seed(tmp_path)
    started = datetime.now(UTC)
    with transactional_session(sessions) as session:
        repositories = SQLAlchemyRepositories(session)
        claimed = repositories.claim_next_job("worker-a", started, started + timedelta(seconds=10))
        assert claimed is not None
        first_fence = job_fence_from_job(claimed)
        assert repositories.inspect_job_fence(first_fence, started) is LeaseCheckResult.VALID
        assert (
            repositories.inspect_job_fence(first_fence, started + timedelta(seconds=11))
            is LeaseCheckResult.LEASE_EXPIRED
        )

    recovered_at = started + timedelta(seconds=11)
    with transactional_session(sessions) as session:
        repositories = SQLAlchemyRepositories(session)
        recovered = repositories.claim_next_job(
            "worker-b", recovered_at, recovered_at + timedelta(minutes=1)
        )
        assert recovered is not None
        assert (
            repositories.inspect_job_fence(first_fence, recovered_at)
            is LeaseCheckResult.LEASE_OWNERSHIP_LOST
        )


def test_delete_request_is_observed_as_cancel_and_reaches_terminal_state(
    tmp_path: Path,
) -> None:
    """中文：删除请求优先表现为取消，当前代次可安全写入 CANCELLED。

    English: Deletion is observed as cancellation and the current generation may close it.
    """

    sessions = _seed(tmp_path)
    now = datetime.now(UTC)
    with transactional_session(sessions) as session:
        repositories = SQLAlchemyRepositories(session)
        claimed = repositories.claim_next_job("worker-a", now, now + timedelta(minutes=1))
        assert claimed is not None
        fence = job_fence_from_job(claimed)
    with transactional_session(sessions) as session:
        repositories = SQLAlchemyRepositories(session)
        repositories.request_document_deletion("tenant-a", "document-a", now)
        assert repositories.inspect_job_fence(fence, now) is LeaseCheckResult.CANCEL_REQUESTED
        repositories.mark_job_cancelled(fence, now, "document_deleted")
    with transactional_session(sessions) as session:
        job = SQLAlchemyRepositories(session).get_job("tenant-a", "job-a")
        assert job is not None and job.status is JobStatus.CANCELLED
        document = SQLAlchemyRepositories(session).get_document("tenant-a", "document-a")
        assert document is not None and document.status is DocumentStatus.PENDING_DELETE
