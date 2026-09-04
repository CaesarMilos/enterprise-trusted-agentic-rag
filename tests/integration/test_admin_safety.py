"""中文：验证管理员无变化操作和空索引发布的安全约束。

English: Verify admin no-op behavior and empty-index publication safeguards.
"""

from pathlib import Path
from typing import cast

import pytest

from enterprise_rag.core.enums import ContentProfile, SourceVisibility
from enterprise_rag.core.exceptions import ValidationError
from enterprise_rag.domain.models import Source, UserContext
from enterprise_rag.domain.results import IndexBuildResult
from enterprise_rag.indexing.index_coordinator import IndexCoordinator
from enterprise_rag.infrastructure.persistence.database import (
    create_database_engine,
    create_session_factory,
    initialize_database,
    transactional_session,
)
from enterprise_rag.infrastructure.persistence.orm_models import TenantRow
from enterprise_rag.infrastructure.persistence.repositories import SQLAlchemyRepositories
from enterprise_rag.services.knowledge_service import IndexBuildService, KnowledgeService


def _sessions(tmp_path: Path):
    """中文：创建包含一个租户和一个法规来源的隔离数据库。

    English: Create an isolated database with one tenant and regulation source.
    """

    engine = create_database_engine(f"sqlite:///{tmp_path / 'admin.db'}")
    initialize_database(engine)
    sessions = create_session_factory(engine)
    with transactional_session(sessions) as session:
        session.add(TenantRow(id="tenant-a", name="Tenant A", is_active=True))
        session.flush()
        SQLAlchemyRepositories(session).add_source(
            Source(
                "source-a",
                "tenant-a",
                "Civil Code",
                "Regulations",
                content_profile=ContentProfile.REGULATION,
                visibility=SourceVisibility.TENANT,
            )
        )
    return sessions


def test_unchanged_source_profile_does_not_require_reprocessing(tmp_path: Path) -> None:
    """中文：重复提交相同画像时不得误报需要重新处理。

    English: Re-submitting an identical profile must not falsely require reprocessing.
    """

    sessions = _sessions(tmp_path)
    service = KnowledgeService(
        sessions,
        lambda tenant_id: IndexBuildResult("unused", 0, False, None),
    )
    user = UserContext("admin-a", "tenant-a", frozenset({"admin"}))

    result = service.update_source_content_profile(
        user,
        "source-a",
        ContentProfile.REGULATION,
    )

    assert result["requires_reprocessing"] is False


def test_manual_empty_index_rebuild_is_blocked(tmp_path: Path) -> None:
    """中文：没有 READY Chunk 时，管理员手动重建不得替换当前索引。

    English: Without READY chunks, a manual rebuild must not replace the active index.
    """

    sessions = _sessions(tmp_path)
    # 中文：空索引检查发生在协调器调用前，因此测试替身不会被解引用。
    # English: The empty-index guard runs before the coordinator, so this sentinel is untouched.
    coordinator = cast(IndexCoordinator, object())
    service = IndexBuildService(sessions, coordinator, "embed", "chunk", "config")

    with pytest.raises(ValidationError) as raised:
        service.rebuild_active("tenant-a")

    assert raised.value.detail.code == "EMPTY_INDEX_REBUILD_BLOCKED"
