"""中文：本模块负责实现“数据库”相关功能。

English: Create SQLAlchemy engines, sessions, schema, and explicit transaction boundaries.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from enterprise_rag.infrastructure.persistence.migrations import upgrade_database


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
    """中文：通过正式 Alembic revision 初始化空库或接管已验证 V4 库。

    English: Initialize an empty database or adopt a verified V4 database through Alembic.
    """

    upgrade_database(engine, adopt_v4=True)


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
