"""中文：验证文档删除的立即撤销、持久任务和最终终态。

English: Verify immediate revocation, durable asynchronous deletion, and terminal state.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from enterprise_rag.core.enums import DocumentStatus, JobStatus, JobType, SourceVisibility
from enterprise_rag.domain.models import (
    Document,
    DocumentVersion,
    Source,
    UserContext,
    job_fence_from_job,
)
from enterprise_rag.domain.results import IndexBuildResult
from enterprise_rag.infrastructure.persistence.database import (
    create_database_engine,
    create_session_factory,
    initialize_database,
    transactional_session,
)
from enterprise_rag.infrastructure.persistence.orm_models import TenantRow
from enterprise_rag.infrastructure.persistence.repositories import SQLAlchemyRepositories
from enterprise_rag.services.knowledge_service import KnowledgeService


def test_delete_returns_job_and_worker_reaches_deleted(tmp_path: Path) -> None:
    """中文：接口阶段立即 PENDING_DELETE，Worker 后续提交 DELETED/SUCCEEDED。

    English: Request becomes PENDING_DELETE immediately; the worker later commits
    DELETED/SUCCEEDED.
    """

    engine = create_database_engine(f"sqlite:///{tmp_path / 'delete.db'}")
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
        repositories.add_document(
            Document(
                "document-a",
                "tenant-a",
                "source-a",
                "Manual",
                status=DocumentStatus.READY,
                active_version_id="version-a",
            )
        )
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
    rebuilt: list[str] = []
    cleaned: list[tuple[str, ...]] = []
    service = KnowledgeService(
        sessions,
        lambda tenant_id: (
            rebuilt.append(tenant_id) or IndexBuildResult("index-new", 0, True, "index-old")
        ),
        cleanup_files=lambda tenant_id, keys: cleaned.append(keys),
    )
    user = UserContext("admin", "tenant-a", frozenset({"admin"}))

    accepted = service.delete_document(user, "document-a", "delete-request-a")
    with transactional_session(sessions) as session:
        repositories = SQLAlchemyRepositories(session)
        document = repositories.get_document("tenant-a", "document-a")
        assert document is not None and document.status is DocumentStatus.PENDING_DELETE
        claimed = repositories.claim_next_job(
            "worker-a",
            datetime.now(UTC),
            datetime.now(UTC) + timedelta(minutes=1),
        )
        assert claimed is not None and claimed.job_type is JobType.DELETION
        fence = job_fence_from_job(claimed)

    service.process_deletion_job(claimed, fence)

    with transactional_session(sessions) as session:
        repositories = SQLAlchemyRepositories(session)
        document = repositories.get_document("tenant-a", "document-a")
        job = repositories.get_job("tenant-a", accepted.deletion_job_id)
        assert document is not None and document.status is DocumentStatus.DELETED
        assert job is not None and job.status is JobStatus.SUCCEEDED
        assert repositories.current_revocation_epoch("tenant-a") == 1
    assert rebuilt == ["tenant-a"]
    assert cleaned == [("storage-a",)]
