"""中文：一键创建本地运行目录、执行 Alembic 并幂等初始化 Demo 租户。

English: Create local runtime directories, run Alembic, and idempotently seed the demo tenant.
"""

from __future__ import annotations

from enterprise_rag.api.dependencies import default_settings
from enterprise_rag.core.enums import ContentProfile, SourceVisibility
from enterprise_rag.core.ids import stable_id
from enterprise_rag.domain.models import Source
from enterprise_rag.infrastructure.persistence.database import (
    create_database_engine,
    create_session_factory,
    transactional_session,
)
from enterprise_rag.infrastructure.persistence.migrations import upgrade_database
from enterprise_rag.infrastructure.persistence.orm_models import TenantRow
from enterprise_rag.infrastructure.persistence.repositories import SQLAlchemyRepositories


def main() -> None:
    """中文：在不加载模型的情况下完成开发环境初始化。

    English: Bootstrap development metadata without loading model providers.
    """

    settings = default_settings()
    for directory in (
        settings.storage.upload_dir,
        settings.storage.index_dir,
        settings.storage.trace_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    engine = create_database_engine(settings.storage.database_url)
    upgrade_database(engine, adopt_v4=True)
    tenant_id = settings.security.default_tenant_id
    source_name = "Enterprise Reference Documents"
    source_id = stable_id("src", (tenant_id, source_name))
    # 中文：临时 Session 工厂仅用于这个短初始化事务。
    # English: The temporary session factory exists only for this short seed transaction.
    sessions = create_session_factory(engine)
    with transactional_session(sessions) as session:
        tenant = session.get(TenantRow, tenant_id)
        if tenant is None:
            session.add(TenantRow(id=tenant_id, name="Development Tenant", is_active=True))
            session.flush()
        repositories = SQLAlchemyRepositories(session)
        if repositories.get_source(tenant_id, source_id) is None:
            repositories.add_source(
                Source(
                    id=source_id,
                    tenant_id=tenant_id,
                    name=source_name,
                    description=(
                        "Regulations, technical manuals, device instructions, procedures, "
                        "and general enterprise reference documents."
                    ),
                    content_profile=ContentProfile.GENERAL_PROSE,
                    visibility=SourceVisibility.TENANT,
                )
            )
    print(f"Development environment ready: tenant={tenant_id} source={source_id}")


if __name__ == "__main__":
    main()
