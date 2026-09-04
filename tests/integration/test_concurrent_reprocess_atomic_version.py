"""中文：验证并发重处理使用数据库原子版本分配器。

English: Verify concurrent reprocessing uses the database-backed atomic version allocator.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from enterprise_rag.domain.models import Document, Source
from enterprise_rag.infrastructure.persistence.database import (
    create_database_engine,
    create_session_factory,
    initialize_database,
    transactional_session,
)
from enterprise_rag.infrastructure.persistence.orm_models import TenantRow
from enterprise_rag.infrastructure.persistence.repositories import SQLAlchemyRepositories


def _seed(tmp_path: Path) -> sessionmaker[Session]:
    """中文：创建已经占用版本 1 的逻辑文档。

    English: Create a logical document whose version one is already reserved.
    """

    engine = create_database_engine(f"sqlite:///{tmp_path / 'atomic-version.db'}")
    initialize_database(engine)
    sessions = create_session_factory(engine)
    with transactional_session(sessions) as session:
        session.add(TenantRow(id="tenant-a", name="Tenant A", is_active=True))
        session.flush()
        repositories = SQLAlchemyRepositories(session)
        repositories.add_source(Source("source-a", "tenant-a", "Manuals", "Manuals"))
        repositories.add_document(Document("document-a", "tenant-a", "source-a", "Manual"))
    return sessions


def test_concurrent_allocations_are_unique_and_monotonic(tmp_path: Path) -> None:
    """中文：两个并发事务必须得到 2 和 3，不能重复分配。

    English: Two concurrent transactions must receive two and three without duplication.
    """

    sessions = _seed(tmp_path)

    def allocate() -> int:
        """中文：在独立短事务中分配一次版本号。

        English: Allocate one version number in an independent short transaction.
        """

        with transactional_session(sessions) as session:
            return SQLAlchemyRepositories(session).next_version_number("tenant-a", "document-a")

    with ThreadPoolExecutor(max_workers=2) as executor:
        allocated = tuple(executor.map(lambda _: allocate(), range(2)))

    assert sorted(allocated) == [2, 3]
    with transactional_session(sessions) as session:
        document = SQLAlchemyRepositories(session).get_document("tenant-a", "document-a")
        assert document is not None and document.next_version_number == 4
