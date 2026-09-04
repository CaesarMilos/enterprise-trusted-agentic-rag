"""中文：本模块负责实现“测试持久化”相关功能。

English: Verify tenant isolation and deletion exclusion through the real SQLite persistence
layer.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier

from enterprise_rag.core.enums import (
    ContentProfile,
    DocumentStatus,
    IndexStatus,
    JobStatus,
    SourceVisibility,
)
from enterprise_rag.core.exceptions import StaleIndexBuildPlanError
from enterprise_rag.domain.models import (
    Chunk,
    Document,
    DocumentVersion,
    IndexVersion,
    IngestionJob,
    Source,
    TraceRecord,
)
from enterprise_rag.infrastructure.persistence.database import (
    create_database_engine,
    create_session_factory,
    initialize_database,
    transactional_session,
)
from enterprise_rag.infrastructure.persistence.orm_models import TenantRow
from enterprise_rag.infrastructure.persistence.repositories import SQLAlchemyRepositories


def _sessions(tmp_path: Path):
    """中文：该内部函数负责“数据库会话”相关处理。

    English: Create an isolated initialized SQLite session factory.
    """

    # 中文：变量 `engine` 用于保存“`engine`”相关数据；其精确定义与约束见下方英文说明。
    # English: Database file lives entirely inside the test temporary directory.
    engine = create_database_engine(f"sqlite:///{tmp_path / 'test.db'}")
    initialize_database(engine)
    return create_session_factory(engine)


def _seed_ready_document(sessions, tenant_id: str, source_id: str, document_id: str) -> str:
    """中文：该内部函数负责“种子就绪文档”相关处理。

    English: Persist one ready document, active version, and deterministic chunk.
    """

    # 中文：变量 `version_id` 用于保存“版本标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Version identity is returned for assertions and chunk creation.
    version_id = f"version-{document_id}"
    with transactional_session(sessions) as session:
        session.add(TenantRow(id=tenant_id, name=tenant_id, is_active=True))
        session.flush()
        repositories = SQLAlchemyRepositories(session)
        repositories.add_source(
            Source(
                id=source_id,
                tenant_id=tenant_id,
                name=source_id,
                description="Test source",
                visibility=SourceVisibility.TENANT,
            )
        )
        repositories.add_document(
            Document(
                id=document_id,
                tenant_id=tenant_id,
                source_id=source_id,
                title="Policy",
                status=DocumentStatus.READY,
                active_version_id=version_id,
            )
        )
        repositories.add_version(
            DocumentVersion(
                id=version_id,
                tenant_id=tenant_id,
                document_id=document_id,
                source_id=source_id,
                version_number=1,
                original_filename="policy.txt",
                media_type="txt",
                content_hash="hash",
                storage_key="key",
                size_bytes=10,
            )
        )
        repositories.replace_version_chunks(
            tenant_id,
            version_id,
            (
                Chunk(
                    id=f"chunk-{document_id}",
                    tenant_id=tenant_id,
                    source_id=source_id,
                    document_id=document_id,
                    document_version_id=version_id,
                    ordinal=0,
                    text="Policy evidence",
                    token_count=2,
                    page_start=None,
                    page_end=None,
                    heading_path=(),
                    previous_chunk_id=None,
                    next_chunk_id=None,
                    boundary_reason="document_end",
                    chunker_version="test-v1",
                    content_hash="chunk-hash",
                ),
            ),
        )
    return version_id


def test_repository_hides_cross_tenant_documents(tmp_path: Path) -> None:
    """中文：该测试用于验证“仓储隐藏交叉租户文档”相关行为。

    English: Ensure tenant predicates prevent existence disclosure by globally unique IDs.
    """

    sessions = _sessions(tmp_path)
    _seed_ready_document(sessions, "tenant-a", "source-a", "document-a")

    with transactional_session(sessions) as session:
        repositories = SQLAlchemyRepositories(session)
        assert repositories.get_document("tenant-a", "document-a") is not None
        assert repositories.get_document("tenant-b", "document-a") is None


def test_source_content_profile_round_trips_through_sqlite(tmp_path: Path) -> None:
    """中文：确认管理员更新的内容画像可持久化并按租户读取。

    English: Ensure an administrator-selected content profile persists within tenant scope.
    """

    sessions = _sessions(tmp_path)
    _seed_ready_document(sessions, "tenant-a", "source-a", "document-a")

    with transactional_session(sessions) as session:
        repositories = SQLAlchemyRepositories(session)
        updated = repositories.update_source_content_profile(
            "tenant-a",
            "source-a",
            ContentProfile.MANUAL,
        )
        assert updated is not None
        assert updated.content_profile is ContentProfile.MANUAL

    with transactional_session(sessions) as session:
        loaded = SQLAlchemyRepositories(session).get_source("tenant-a", "source-a")
        assert loaded is not None
        assert loaded.content_profile is ContentProfile.MANUAL


def test_trace_snapshot_identity_round_trips_through_sqlite(tmp_path: Path) -> None:
    """中文：查询快照标识必须写入正式列并能够完整读回。

    English: Query snapshot identity must persist in its dedicated column and round-trip.
    """

    sessions = _sessions(tmp_path)
    _seed_ready_document(sessions, "tenant-a", "source-a", "document-a")
    with transactional_session(sessions) as session:
        SQLAlchemyRepositories(session).add_trace(
            TraceRecord(
                id="trace-a",
                tenant_id="tenant-a",
                user_id="user-a",
                operation="chat",
                status="started",
                index_version_id="index-a",
                snapshot_id="snapshot-a",
            )
        )

    with transactional_session(sessions) as session:
        loaded = SQLAlchemyRepositories(session).get_trace("tenant-a", "trace-a")

    assert loaded is not None
    assert loaded.index_version_id == "index-a"
    assert loaded.snapshot_id == "snapshot-a"


def test_pending_delete_immediately_disappears_from_active_chunks(tmp_path: Path) -> None:
    """中文：该测试用于验证“待处理的删除立即`disappears`从活动文本块”相关行为。

    English: Ensure ACL/index rebuild reads cannot include a document awaiting deletion.
    """

    sessions = _sessions(tmp_path)
    _seed_ready_document(sessions, "tenant-a", "source-a", "document-a")

    with transactional_session(sessions) as session:
        repositories = SQLAlchemyRepositories(session)
        assert len(repositories.list_active_chunks("tenant-a")) == 1
        repositories.set_document_status(
            "tenant-a",
            "document-a",
            DocumentStatus.PENDING_DELETE,
        )

    with transactional_session(sessions) as session:
        repositories = SQLAlchemyRepositories(session)
        assert repositories.list_active_chunks("tenant-a") == ()
        assert repositories.get_chunks("tenant-a", ("chunk-document-a",)) == ()
        assert (
            repositories.get_retrievable_chunks(
                "tenant-a",
                ("chunk-document-a",),
            )
            == ()
        )


def test_sqlite_job_claim_cannot_return_the_same_job_twice(tmp_path: Path) -> None:
    """中文：确认 SQLite 条件更新领取后，后续 Worker 不能重复获得同一任务。

    English: Ensure SQLite conditional claiming prevents a later worker from receiving the same
    job twice.
    """

    sessions = _sessions(tmp_path)
    version_id = _seed_ready_document(sessions, "tenant-a", "source-a", "document-a")
    with transactional_session(sessions) as session:
        SQLAlchemyRepositories(session).add_job(
            IngestionJob(
                id="job-a",
                tenant_id="tenant-a",
                document_id="document-a",
                document_version_id=version_id,
                status=JobStatus.PENDING,
            )
        )

    now = datetime.now(UTC)
    with transactional_session(sessions) as session:
        first = SQLAlchemyRepositories(session).claim_next_job(
            "worker-a",
            now,
            now + timedelta(seconds=60),
        )
        assert first is not None and first.id == "job-a"
    with transactional_session(sessions) as session:
        second = SQLAlchemyRepositories(session).claim_next_job(
            "worker-b",
            now,
            now + timedelta(seconds=60),
        )
        assert second is None


def test_stale_index_activation_is_rejected_optimistically(tmp_path: Path) -> None:
    """中文：确认两个旧快照构建计划不能依次覆盖新的活动索引。

    English: Ensure two plans built from the same old snapshot cannot overwrite the newer active
    index in sequence.
    """

    sessions = _sessions(tmp_path)
    with transactional_session(sessions) as session:
        session.add(TenantRow(id="tenant-a", name="tenant-a", is_active=True))
    with transactional_session(sessions) as session:
        repositories = SQLAlchemyRepositories(session)
        repositories.add_index(
            IndexVersion(
                id="index-old",
                tenant_id="tenant-a",
                status=IndexStatus.ACTIVE,
                storage_key="index-old",
                chunk_count=1,
                config_fingerprint="config-a",
            )
        )
        for index_id in ("index-new-a", "index-new-b"):
            repositories.add_index(
                IndexVersion(
                    id=index_id,
                    tenant_id="tenant-a",
                    status=IndexStatus.READY,
                    storage_key=index_id,
                    chunk_count=1,
                    config_fingerprint="config-a",
                )
            )

    with transactional_session(sessions) as session:
        repositories = SQLAlchemyRepositories(session)
        repositories.activate_index("tenant-a", "index-new-a", "index-old")
    try:
        with transactional_session(sessions) as session:
            SQLAlchemyRepositories(session).activate_index(
                "tenant-a",
                "index-new-b",
                "index-old",
            )
    except StaleIndexBuildPlanError as exc:
        assert exc.detail.code == "STALE_INDEX_BUILD_PLAN"
    else:
        raise AssertionError("stale index activation must fail")

    with transactional_session(sessions) as session:
        active = SQLAlchemyRepositories(session).get_active_index("tenant-a")
        assert active is not None and active.id == "index-new-a"


def test_concurrent_index_activations_leave_exactly_one_winner(tmp_path: Path) -> None:
    """中文：确认同一旧快照构建的两个并发计划只能有一个激活。

    English: Ensure only one of two plans built from the same old snapshot can activate.
    """

    sessions = _sessions(tmp_path)
    with transactional_session(sessions) as session:
        session.add(TenantRow(id="tenant-a", name="tenant-a", is_active=True))
    with transactional_session(sessions) as session:
        repositories = SQLAlchemyRepositories(session)
        for index_id, index_status in (
            ("index-old", IndexStatus.ACTIVE),
            ("index-new-a", IndexStatus.READY),
            ("index-new-b", IndexStatus.READY),
        ):
            repositories.add_index(
                IndexVersion(
                    id=index_id,
                    tenant_id="tenant-a",
                    status=index_status,
                    storage_key=index_id,
                    chunk_count=0,
                    config_fingerprint="config-a",
                )
            )

    # 中文：关键变量 `start_barrier` 让两个事务尽可能同时发起。
    # English: Key variable `start_barrier` launches both transactions as concurrently as possible.
    start_barrier = Barrier(2)

    def activate(index_id: str) -> str:
        """中文：在独立 Session 中尝试一次并发索引激活。

        English: Attempt one concurrent index activation in an independent session.
        """

        start_barrier.wait()
        try:
            with transactional_session(sessions) as session:
                SQLAlchemyRepositories(session).activate_index(
                    "tenant-a",
                    index_id,
                    "index-old",
                )
        except StaleIndexBuildPlanError:
            return "stale"
        return "activated"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(activate, ("index-new-a", "index-new-b")))

    assert sorted(results) == ["activated", "stale"]
    with transactional_session(sessions) as session:
        indexes = SQLAlchemyRepositories(session).list_indexes("tenant-a")
        assert sum(index.status is IndexStatus.ACTIVE for index in indexes) == 1
