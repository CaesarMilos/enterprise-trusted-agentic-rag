"""中文：配置 Alembic 在线/离线迁移环境和 V5 ORM 元数据。

English: Configure Alembic online/offline migrations and V5 ORM metadata.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, engine_from_config, pool

from enterprise_rag.infrastructure.persistence.orm_models import Base

# 中文：关键变量 `config` 是 Alembic 当前运行配置，也可由应用注入现有连接。
# English: Key variable `config` is the active Alembic configuration and may carry a connection.
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 中文：自动生成只比较统一 ORM 元数据，正式 revision 仍需人工审查。
# English: Autogeneration compares unified ORM metadata; revisions still require manual review.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """中文：以 URL 生成离线 SQL，不建立数据库连接。

    English: Generate offline SQL from the configured URL without opening a connection.
    """

    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_with_connection(connection: Connection) -> None:
    """中文：在调用方连接中执行迁移，使接管、升级和失败回滚边界明确。

    English: Run migrations on a caller connection for explicit adoption and rollback boundaries.
    """

    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """中文：复用应用连接，或按配置创建一次性迁移引擎。

    English: Reuse an application connection or create a migration-only engine from config.
    """

    supplied_connection = config.attributes.get("connection")
    if isinstance(supplied_connection, Connection):
        _run_with_connection(supplied_connection)
        return
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        _run_with_connection(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
