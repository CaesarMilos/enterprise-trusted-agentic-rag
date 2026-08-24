"""中文：本模块验证租约过期、任务重领与旧 Worker fencing 拒绝语义。

English: Verify lease expiration, job recovery, and stale-worker fencing rejection semantics.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from enterprise_rag.core.enums import DocumentStatus, IndexStatus, JobStatus, SourceVisibility
from enterprise_rag.core.exceptions import LeaseLostError
from enterprise_rag.domain.models import (
    Document,
    DocumentVersion,
    IndexVersion,
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


def _seed_pending_job(tmp_path: Path) -> sessionmaker[Session]:
    """中文：创建一套隔离 SQLite 元数据并返回包含待处理任务的会话工厂。

    English: Create isolated SQLite metadata and return a session factory with a pending job.
    """

    engine = create_database_engine(f"sqlite:///{tmp_path / 'fencing.db'}")
    initialize_database(engine)
    sessions = create_session_factory(engine)
    with transactional_session(sessions) as session:
        session.add(TenantRow(id="tenant-a", name="Tenant A", is_active=True))
        session.flush()
        repositories = SQLAlchemyRepositories(session)
        repositories.add_source(
            Source(
                id="source-a",
                tenant_id="tenant-a",
                name="Manuals",
                description="Fencing test source",
                visibility=SourceVisibility.TENANT,
            )
        )
        repositories.add_document(
            Document(
                id="document-a",
                tenant_id="tenant-a",
                source_id="source-a",
                title="Manual",
                status=DocumentStatus.PENDING,
            )
        )
        repositories.add_version(
            DocumentVersion(
                id="version-a",
                tenant_id="tenant-a",
                document_id="document-a",
                source_id="source-a",
                version_number=1,
                original_filename="manual.txt",
                media_type="txt",
                content_hash="hash",
                storage_key="storage-key",
                size_bytes=10,
            )
        )
        repositories.add_job(
            IngestionJob(
                id="job-a",
                tenant_id="tenant-a",
                document_id="document-a",
                document_version_id="version-a",
                status=JobStatus.PENDING,
            )
        )
    return sessions


def test_expired_worker_cannot_write_or_overwrite_new_attempt(tmp_path: Path) -> None:
    """中文：确认 attempt=1 在 attempt=2 领取后不能写 Chunk 或覆盖终态。

    English: Ensure attempt one cannot write chunks or overwrite state after attempt two claims.
    """

    sessions = _seed_pending_job(tmp_path)
    started = datetime.now(UTC)
    with transactional_session(sessions) as session:
        first_job = SQLAlchemyRepositories(session).claim_next_job(
            "worker-a",
            started,
            started + timedelta(seconds=1),
        )
        assert first_job is not None
        first_fence = job_fence_from_job(first_job)

    recovered_at = started + timedelta(seconds=2)
    with transactional_session(sessions) as session:
        second_job = SQLAlchemyRepositories(session).claim_next_job(
            "worker-b",
            recovered_at,
            recovered_at + timedelta(seconds=60),
        )
        assert second_job is not None
        second_fence = job_fence_from_job(second_job)
        assert second_fence.attempt_count == first_fence.attempt_count + 1

    with pytest.raises(LeaseLostError):
        with transactional_session(sessions) as session:
            SQLAlchemyRepositories(session).replace_version_chunks_fenced(
                first_fence,
                "version-a",
                (),
                recovered_at,
            )

    with pytest.raises(LeaseLostError):
        with transactional_session(sessions) as session:
            SQLAlchemyRepositories(session).mark_job_failed(
                first_fence,
                recovered_at,
                "STALE_WORKER",
                "A stale worker must not own this terminal transition.",
            )

    with transactional_session(sessions) as session:
        SQLAlchemyRepositories(session).mark_job_succeeded(
            second_fence,
            recovered_at + timedelta(seconds=1),
        )
    with transactional_session(sessions) as session:
        job = SQLAlchemyRepositories(session).get_job("tenant-a", "job-a")
        assert job is not None and job.status is JobStatus.SUCCEEDED


def test_lease_renewal_prevents_recovery_before_new_deadline(tmp_path: Path) -> None:
    """中文：确认成功心跳续租后，其他 Worker 不能按旧到期时间重领任务。

    English: Ensure a successful heartbeat prevents recovery at the original expiration time.
    """

    sessions = _seed_pending_job(tmp_path)
    started = datetime.now(UTC)
    with transactional_session(sessions) as session:
        job = SQLAlchemyRepositories(session).claim_next_job(
            "worker-a",
            started,
            started + timedelta(seconds=30),
        )
        assert job is not None
        fence = job_fence_from_job(job)

    heartbeat_at = started + timedelta(seconds=10)
    with transactional_session(sessions) as session:
        renewed = SQLAlchemyRepositories(session).renew_job_lease(
            fence,
            heartbeat_at,
            started + timedelta(seconds=70),
        )
        assert renewed

    with transactional_session(sessions) as session:
        recovered = SQLAlchemyRepositories(session).claim_next_job(
            "worker-b",
            started + timedelta(seconds=31),
            started + timedelta(seconds=91),
        )
        assert recovered is None


def test_stale_worker_cannot_activate_an_index_snapshot(tmp_path: Path) -> None:
    """中文：确认旧 Worker 在新代次领取后无法执行索引激活事务。

    English: Ensure a stale worker cannot activate an index after a new attempt takes ownership.
    """

    sessions = _seed_pending_job(tmp_path)
    started = datetime.now(UTC)
    with transactional_session(sessions) as session:
        repositories = SQLAlchemyRepositories(session)
        first_job = repositories.claim_next_job(
            "worker-a",
            started,
            started + timedelta(seconds=1),
        )
        assert first_job is not None
        first_fence = job_fence_from_job(first_job)
        repositories.add_index(
            IndexVersion(
                id="index-old",
                tenant_id="tenant-a",
                status=IndexStatus.ACTIVE,
                storage_key="index-old",
                chunk_count=0,
                config_fingerprint="config-a",
            )
        )
        repositories.add_index(
            IndexVersion(
                id="index-new",
                tenant_id="tenant-a",
                status=IndexStatus.READY,
                storage_key="index-new",
                chunk_count=0,
                config_fingerprint="config-a",
            )
        )

    recovered_at = started + timedelta(seconds=2)
    with transactional_session(sessions) as session:
        recovered = SQLAlchemyRepositories(session).claim_next_job(
            "worker-b",
            recovered_at,
            recovered_at + timedelta(seconds=60),
        )
        assert recovered is not None

    with pytest.raises(LeaseLostError):
        with transactional_session(sessions) as session:
            repositories = SQLAlchemyRepositories(session)
            repositories.assert_job_fence(first_fence, recovered_at)
            repositories.activate_index("tenant-a", "index-new", "index-old")

    with transactional_session(sessions) as session:
        active = SQLAlchemyRepositories(session).get_active_index("tenant-a")
        assert active is not None and active.id == "index-old"
