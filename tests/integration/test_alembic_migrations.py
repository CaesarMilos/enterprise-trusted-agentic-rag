"""中文：验证 Alembic 空库初始化、V4 接管和未知 Schema 拒绝。

English: Verify Alembic fresh initialization, V4 adoption, and unknown-schema rejection.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import inspect, text

from enterprise_rag.core.exceptions import MigrationStateError
from enterprise_rag.infrastructure.persistence.database import (
    create_database_engine,
    initialize_database,
)
from enterprise_rag.infrastructure.persistence.migrations import (
    _alembic_config,
    assert_database_current,
)


def test_fresh_database_upgrades_to_head(tmp_path: Path) -> None:
    """中文：全新 SQLite 必须只通过 revision 链创建完整 V5 Schema。

    English: A fresh SQLite database must reach the complete V5 schema through revisions only.
    """

    engine = create_database_engine(f"sqlite:///{tmp_path / 'fresh.db'}")
    initialize_database(engine)

    tables = frozenset(inspect(engine).get_table_names())
    assert {"alembic_version", "query_snapshots", "revocations", "quality_reports"} <= tables
    assert_database_current(engine)


def test_unversioned_v4_database_is_validated_adopted_and_backfilled(
    tmp_path: Path,
) -> None:
    """中文：已知 V4 库接管后保留数据，并按最大版本回填原子计数器。

    English: A known V4 database preserves data and backfills its atomic counter from max version.
    """

    engine = create_database_engine(f"sqlite:///{tmp_path / 'legacy-v4.db'}")
    with engine.begin() as connection:
        command.upgrade(_alembic_config(connection), "0001_v4_baseline")
        connection.execute(
            text(
                "INSERT INTO tenants(id,name,is_active,created_at) "
                "VALUES ('tenant-a','Tenant A',1,CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO sources(id,tenant_id,name,description,content_profile,"
                "chunk_strategy_override,visibility,allowed_group_ids,is_active,created_at) "
                "VALUES ('source-a','tenant-a','Manuals','','manual',NULL,'tenant','[]',1,"
                "CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO documents(id,tenant_id,source_id,title,status,active_version_id,"
                "lifecycle_generation,delete_requested_at,deleted_at,created_at,updated_at) "
                "VALUES ('document-a','tenant-a','source-a','Manual','ready',NULL,0,NULL,NULL,"
                "CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO document_versions(id,tenant_id,document_id,source_id,"
                "version_number,original_filename,media_type,content_hash,storage_key,size_bytes,"
                "ingestion_snapshot,created_at) VALUES ('version-7','tenant-a','document-a',"
                "'source-a',7,'manual.pdf','pdf','hash','storage',10,'{}',CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(text("DROP TABLE alembic_version"))

    initialize_database(engine)

    with engine.connect() as connection:
        counter = connection.scalar(
            text("SELECT next_version_number FROM documents WHERE id = 'document-a'")
        )
        assert counter == 8
    assert_database_current(engine)


def test_unknown_unversioned_schema_is_rejected(tmp_path: Path) -> None:
    """中文：未知表结构不得被盲目 stamp 为 V4。

    English: An unknown schema must never be blindly stamped as V4.
    """

    engine = create_database_engine(f"sqlite:///{tmp_path / 'unknown.db'}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE unrelated(id INTEGER PRIMARY KEY)"))

    with pytest.raises(MigrationStateError):
        initialize_database(engine)
