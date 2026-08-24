"""中文：本模块负责实现“数据库”相关功能。

English: Create SQLAlchemy engines, sessions, schema, and explicit transaction boundaries.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from enterprise_rag.infrastructure.persistence.orm_models import Base


def create_database_engine(database_url: str, echo: bool = False) -> Engine:
    """中文：该函数或方法负责“创建数据库引擎”相关处理。

    English: Create an engine with SQLite foreign keys and production-safe connection checks.
    """

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


def _migrate_source_content_profile_columns(engine: Engine) -> None:
    """中文：为旧数据库补充 V0.2 内容画像列并保留全部已有资料源。

    English: Add V0.2 source-profile columns to legacy databases without deleting data.
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
    """中文：为旧数据库补充 V0.3 接入策略快照 JSON 列。

    English: Add the V0.3 ingestion-strategy snapshot JSON column to legacy databases.
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
