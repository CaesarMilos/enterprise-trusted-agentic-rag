"""中文：本模块负责实现“数据库”相关功能。

English: Create SQLAlchemy engines, sessions, schema, and explicit transaction boundaries.
"""

from __future__ import annotations

from pathlib import Path

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from enterprise_rag.infrastructure.persistence.orm_models import Base


def create_database_engine(database_url: str, echo: bool = False) -> Engine:
    """中文：该函数或方法负责“创建数据库引擎”相关处理。

    English: Create an engine with SQLite foreign keys and production-safe connection checks.
    """

    # 中文：全新本地部署首次启动时，SQLite 不会自动创建数据库父目录，
    # 因此必须在建立数据库连接前创建目录。
    # English: SQLite cannot create a missing parent directory, so bootstrap it
    # before opening the database during a fresh local deployment.
    if database_url.startswith("sqlite:///") and ":memory:" not in database_url:
        database_path = Path(database_url.removeprefix("sqlite:///")).expanduser()
        database_path.resolve().parent.mkdir(parents=True, exist_ok=True)

    # 中文：变量 `connect_args` 用于保存“`connect``args`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: SQLite requires a thread override when FastAPI and worker threads share the
    #   engine.
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    # 中文：变量 `engine` 用于保存“`engine`”相关数据；其精确定义与约束见下方英文说明。
    # English: Future-style SQLAlchemy engine is the sole owner of pooled connections.
    engine = create_engine(
        database_url,
        echo=echo,
        pool_pre_ping=True,
        connect_args=connect_args,
    )
    if database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def enable_sqlite_foreign_keys(dbapi_connection: object, _: object) -> None:
            """中文：该函数或方法负责“启用SQLite外键键”相关处理。

            English: Enable foreign-key enforcement for each newly opened SQLite connection.
            """

            # 中文：变量 `cursor` 用于保存“`cursor`”相关数据；其精确定义与约束见下方英文说明。
            # English: DB-API connection exposes cursor at runtime; annotation remains
            #   adapter-neutral.
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """中文：该函数或方法负责“创建会话工厂”相关处理。

    English: Create sessions that retain loaded values after commits.
    """

    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False, autoflush=False)


def initialize_database(engine: Engine) -> None:
    """中文：该函数或方法负责“初始化数据库”相关处理。

    English: Create every declared metadata table for local and test deployments.
    """

    Base.metadata.create_all(engine)
    _migrate_source_content_profile_columns(engine)
    _migrate_document_version_snapshot_column(engine)
    _migrate_v4_lifecycle_columns(engine)


def _migrate_source_content_profile_columns(engine: Engine) -> None:
    """中文：为 V4 之前的数据库补充内容画像列并保留全部已有资料源。

    English: Add source-profile columns to pre-V4 databases without deleting existing data.
    """

    # 中文：变量 `existing_columns` 保存当前 sources 表的真实列名，迁移因此可重复执行。
    # English: Existing column names make this lightweight migration idempotent.
    existing_columns = {column["name"] for column in inspect(engine).get_columns("sources")}
    with engine.begin() as connection:
        if "content_profile" not in existing_columns:
            connection.execute(
                text(
                    "ALTER TABLE sources ADD COLUMN content_profile "
                    "VARCHAR(32) NOT NULL DEFAULT 'general_prose'"
                )
            )
        if "chunk_strategy_override" not in existing_columns:
            connection.execute(
                text("ALTER TABLE sources ADD COLUMN chunk_strategy_override VARCHAR(128)")
            )


def _migrate_document_version_snapshot_column(engine: Engine) -> None:
    """中文：为 V4 之前的数据库补充接入策略快照 JSON 列。

    English: Add the ingestion-strategy snapshot JSON column to pre-V4 databases.
    """

    existing_columns = {
        column["name"] for column in inspect(engine).get_columns("document_versions")
    }
    if "ingestion_snapshot" in existing_columns:
        return
    with engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE document_versions ADD COLUMN ingestion_snapshot JSON "
                "NOT NULL DEFAULT '{}'"
            )
        )


def _migrate_v4_lifecycle_columns(engine: Engine) -> None:
    """中文：幂等补充 V4 文档 fencing、任务取消与索引终态字段。

    English: Idempotently add V4 document fencing, job cancellation, and index terminal fields.

    中文：本发行版以 SQLite 为持久化基线；其他数据库适配器必须提供版本化迁移。
    English: SQLite is this distribution's baseline; other database adapters need migrations.
    """

    # 中文：每张表独立检查列集合，重复启动不会再次执行 ALTER TABLE。
    # English: Each table is inspected independently so repeated startup never repeats ALTERs.
    table_columns = {
        table: {column["name"] for column in inspect(engine).get_columns(table)}
        for table in ("documents", "ingestion_jobs", "index_versions")
    }
    statements = {
        "documents": {
            "lifecycle_generation": (
                "ALTER TABLE documents ADD COLUMN lifecycle_generation INTEGER "
                "NOT NULL DEFAULT 0"
            ),
            "delete_requested_at": (
                "ALTER TABLE documents ADD COLUMN delete_requested_at DATETIME"
            ),
            "deleted_at": "ALTER TABLE documents ADD COLUMN deleted_at DATETIME",
        },
        "ingestion_jobs": {
            "document_generation_snapshot": (
                "ALTER TABLE ingestion_jobs ADD COLUMN document_generation_snapshot INTEGER "
                "NOT NULL DEFAULT 0"
            ),
            "cancel_requested_at": (
                "ALTER TABLE ingestion_jobs ADD COLUMN cancel_requested_at DATETIME"
            ),
            "cancel_reason": (
                "ALTER TABLE ingestion_jobs ADD COLUMN cancel_reason VARCHAR(128)"
            ),
        },
        "index_versions": {
            "error_code": "ALTER TABLE index_versions ADD COLUMN error_code VARCHAR(128)",
            "error_message": "ALTER TABLE index_versions ADD COLUMN error_message TEXT",
            "completed_at": "ALTER TABLE index_versions ADD COLUMN completed_at DATETIME",
        },
    }
    with engine.begin() as connection:
        for table, columns in statements.items():
            for column, statement in columns.items():
                if column not in table_columns[table]:
                    connection.execute(text(statement))


@contextmanager
def transactional_session(factory: sessionmaker[Session]) -> Iterator[Session]:
    """中文：该函数或方法负责“事务化会话”相关处理。

    English: Yield one session and commit or roll back the complete application transaction.
    """

    # 中文：变量 `session` 用于保存“会话”相关数据；其精确定义与约束见下方英文说明。
    # English: One use case owns one session and therefore one explicit transaction
    #   boundary.
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
