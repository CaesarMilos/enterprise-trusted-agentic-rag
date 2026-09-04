"""中文：执行、接管并验证正式 Alembic 数据库迁移。

English: Run, adopt, and verify formal Alembic database migrations.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Engine, inspect

from enterprise_rag.core.enums import ErrorCategory
from enterprise_rag.core.exceptions import MigrationStateError, error_detail

# 中文：V4 接管只接受这些已知业务表，不能对任意未知数据库盲目 stamp。
# English: V4 adoption requires these known business tables and never blindly stamps a database.
_V4_TABLES = frozenset(
    {
        "tenants",
        "sources",
        "documents",
        "document_versions",
        "chunks",
        "ingestion_jobs",
        "index_versions",
        "traces",
    }
)
_V4_REQUIRED_COLUMNS: dict[str, frozenset[str]] = {
    "sources": frozenset({"content_profile", "chunk_strategy_override"}),
    "documents": frozenset({"lifecycle_generation", "delete_requested_at", "deleted_at"}),
    "document_versions": frozenset({"ingestion_snapshot"}),
    "ingestion_jobs": frozenset(
        {"document_generation_snapshot", "cancel_requested_at", "cancel_reason"}
    ),
    "index_versions": frozenset({"error_code", "error_message", "completed_at"}),
}


def _alembic_config(connection: Connection | None = None) -> Config:
    """中文：构建以工程根目录为基准的 Alembic 配置。

    English: Build an Alembic configuration rooted at the project directory.
    """

    project_root = Path(__file__).resolve().parents[4]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "migrations"))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def _has_version_table(connection: Connection) -> bool:
    """中文：判断数据库是否已由 Alembic 管理。

    English: Return whether Alembic already manages this database.
    """

    return "alembic_version" in inspect(connection).get_table_names()


def _validate_v4_baseline(connection: Connection) -> None:
    """中文：接管旧库前校验表和关键列完全符合可识别 V4 基线。

    English: Validate tables and key columns against the recognized V4 baseline before adoption.
    """

    inspector = inspect(connection)
    tables = frozenset(inspector.get_table_names())
    missing_tables = sorted(_V4_TABLES - tables)
    missing_columns = {
        table: sorted(required - {column["name"] for column in inspector.get_columns(table)})
        for table, required in _V4_REQUIRED_COLUMNS.items()
        if table in tables
        and required - {column["name"] for column in inspector.get_columns(table)}
    }
    if missing_tables or missing_columns:
        raise MigrationStateError(
            error_detail(
                "DATABASE_BASELINE_UNKNOWN",
                ErrorCategory.VALIDATION,
                "The existing database does not match the supported V4 migration baseline.",
                missing_tables=",".join(missing_tables),
                missing_columns=str(missing_columns),
            )
        )


def upgrade_database(engine: Engine, *, adopt_v4: bool) -> None:
    """中文：升级空库或已管理库；仅在显式允许时接管已验证 V4 库。

    English: Upgrade empty/managed databases and adopt a verified V4 database only when allowed.
    """

    with engine.begin() as connection:
        tables = frozenset(inspect(connection).get_table_names())
        if tables and not _has_version_table(connection):
            if not adopt_v4:
                raise MigrationStateError(
                    error_detail(
                        "DATABASE_MIGRATION_REQUIRED",
                        ErrorCategory.VALIDATION,
                        "The database must be migrated before production startup.",
                    )
                )
            _validate_v4_baseline(connection)
            command.stamp(_alembic_config(connection), "0001_v4_baseline")
        command.upgrade(_alembic_config(connection), "head")


def assert_database_current(engine: Engine) -> None:
    """中文：生产启动只读校验数据库 revision 等于唯一 Alembic head。

    English: Read-only production startup check requiring the database revision at Alembic head.
    """

    with engine.connect() as connection:
        if not _has_version_table(connection):
            raise MigrationStateError(
                error_detail(
                    "DATABASE_MIGRATION_REQUIRED",
                    ErrorCategory.VALIDATION,
                    "The database has not been initialized by Alembic.",
                )
            )
        current = MigrationContext.configure(connection).get_current_revision()
        heads = ScriptDirectory.from_config(_alembic_config()).get_heads()
        if len(heads) != 1 or current != heads[0]:
            raise MigrationStateError(
                error_detail(
                    "DATABASE_REVISION_MISMATCH",
                    ErrorCategory.VALIDATION,
                    "The database revision does not match the application migration head.",
                    current_revision=str(current),
                    expected_revision=",".join(heads),
                )
            )
