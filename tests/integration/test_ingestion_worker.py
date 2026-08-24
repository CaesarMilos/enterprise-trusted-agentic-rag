"""中文：本模块负责实现“测试资料接入工作进程”相关功能。

English: Verify upload acceptance, durable leasing, parsing, chunk persistence, and final
activation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from enterprise_rag.core.enums import DocumentStatus, SourceVisibility
from enterprise_rag.domain.models import JobFence, Source, UserContext
from enterprise_rag.domain.requests import CreateDocumentCommand, ReprocessDocumentCommand
from enterprise_rag.infrastructure.persistence.database import (
    create_database_engine,
    create_session_factory,
    initialize_database,
    transactional_session,
)
from enterprise_rag.infrastructure.persistence.orm_models import TenantRow
from enterprise_rag.infrastructure.persistence.repositories import SQLAlchemyRepositories
from enterprise_rag.infrastructure.storage.local_file_store import LocalFileStore
from enterprise_rag.ingestion.chunk_strategies import build_default_strategy_registry
from enterprise_rag.ingestion.cleaner import TextCleaner
from enterprise_rag.ingestion.loader_registry import LoaderRegistry
from enterprise_rag.ingestion.loaders.text_loader import TextLoader
from enterprise_rag.ingestion.metadata_extractor import MetadataExtractor
from enterprise_rag.ingestion.pipeline import IngestionPipeline
from enterprise_rag.ingestion.quality_validator import ChunkQualityValidator
from enterprise_rag.ingestion.structure_parser import StructureParser
from enterprise_rag.ingestion.validator import UploadValidator
from enterprise_rag.services.ingestion_service import IngestionService
from enterprise_rag.services.ingestion_worker import IngestionWorker


def test_durable_worker_processes_a_text_upload(tmp_path: Path) -> None:
    """中文：该测试用于验证“持久化工作进程处理一个文本上传”相关行为。

    English: Ensure a persisted job survives the API boundary and reaches a ready document.
    """

    # 中文：变量 `engine` 用于保存“`engine`”相关数据；其精确定义与约束见下方英文说明。
    # English: Isolated database and storage roots avoid external runtime state.
    engine = create_database_engine(f"sqlite:///{tmp_path / 'metadata.db'}")
    initialize_database(engine)
    sessions = create_session_factory(engine)
    file_store = LocalFileStore(tmp_path / "uploads")
    # 中文：本步骤涉及租户、资料源、上传、服务，具体约束见下方英文说明。
    # English: Seed exact tenant and source ownership required by the upload service.
    with transactional_session(sessions) as session:
        session.add(TenantRow(id="tenant-a", name="Tenant A", is_active=True))
        session.flush()
        SQLAlchemyRepositories(session).add_source(
            Source(
                id="source-a",
                tenant_id="tenant-a",
                name="Policies",
                description="Company policy documents",
                visibility=SourceVisibility.TENANT,
            )
        )
    # 中文：变量 `upload_path` 用于保存“上传`path`”相关数据；其精确定义与约束见下方英文说明。
    # English: Temporary upload simulates bytes already received by an HTTP adapter.
    upload_path = tmp_path / "policy.txt"
    upload_path.write_text(
        "Annual leave requires manager approval.\n\nSecurity incidents must be reported.",
        encoding="utf-8",
    )
    service = IngestionService(
        sessions,
        UploadValidator(("txt",), max_file_size_mb=1),
        file_store,
    )
    accepted = service.create_document(
        CreateDocumentCommand(
            user=UserContext(
                user_id="admin-a",
                tenant_id="tenant-a",
                roles=frozenset({"admin"}),
            ),
            source_id="source-a",
            filename="policy.txt",
            temporary_path=upload_path,
        )
    )

    # 中文：函数 `publish` 用于执行“`publish`”相关处理；其精确定义与约束见下方英文说明。
    # English: Test publisher models the required final transaction after a validated
    #   index publication.
    def publish(
        tenant_id: str,
        document_id: str,
        document_version_id: str,
        job_id: str,
        fence: JobFence,
    ) -> None:
        """中文：该函数或方法负责“发布”相关处理。

        English: Atomically mark document version active and durable job successful.
        """

        with transactional_session(sessions) as session:
            repositories = SQLAlchemyRepositories(session)
            repositories.set_document_status(
                tenant_id,
                document_id,
                DocumentStatus.READY,
                active_version_id=document_version_id,
            )
            assert fence.job_id == job_id
            repositories.mark_job_succeeded(fence, datetime.now(UTC))

    pipeline = IngestionPipeline(
        loaders=LoaderRegistry((TextLoader(),)),
        cleaner=TextCleaner(),
        structure_parser=StructureParser(),
        strategy_registry=build_default_strategy_registry(4, 12, 24),
        metadata_extractor=MetadataExtractor(),
        quality_validator=ChunkQualityValidator(),
    )
    worker = IngestionWorker(
        sessions,
        file_store,
        pipeline,
        publish,
        worker_id="worker-a",
        lease_seconds=60,
        heartbeat_seconds=10,
    )

    assert worker.run_once()
    assert not worker.run_once()
    with transactional_session(sessions) as session:
        repositories = SQLAlchemyRepositories(session)
        document = repositories.get_document("tenant-a", accepted.document_id)
        job = repositories.get_job("tenant-a", accepted.job_id)
        chunks = repositories.list_version_chunks(
            "tenant-a",
            accepted.document_version_id,
        )
        assert document is not None and document.status is DocumentStatus.READY
        assert job is not None and job.status.value == "succeeded"
        assert chunks

    # 中文：重新处理创建新版本并复用原始文件，不覆盖首次处理历史。
    # English: Reprocessing creates a new version over the original file without
    #   overwriting history.
    reprocessed = service.reprocess(
        ReprocessDocumentCommand(
            user=UserContext(
                user_id="admin-a",
                tenant_id="tenant-a",
                roles=frozenset({"admin"}),
            ),
            document_id=accepted.document_id,
        )
    )
    assert reprocessed.document_version_id != accepted.document_version_id
    assert worker.run_once()
    with transactional_session(sessions) as session:
        repositories = SQLAlchemyRepositories(session)
        document = repositories.get_document("tenant-a", accepted.document_id)
        chunks = repositories.list_version_chunks(
            "tenant-a",
            reprocessed.document_version_id,
        )
        assert document is not None
        assert document.active_version_id == reprocessed.document_version_id
        assert chunks
        assert all(chunk.metadata["content_profile"] == "general_prose" for chunk in chunks)
