"""中文：本模块负责实现“初始化`db`”相关功能。

English: Initialize local metadata and optionally create the development tenant and source.
"""

from __future__ import annotations

import argparse

from enterprise_rag.api.dependencies import build_container, default_settings
from enterprise_rag.core.enums import ContentProfile, SourceVisibility
from enterprise_rag.core.ids import stable_id
from enterprise_rag.domain.models import Source
from enterprise_rag.infrastructure.persistence.database import transactional_session
from enterprise_rag.infrastructure.persistence.orm_models import TenantRow
from enterprise_rag.infrastructure.persistence.repositories import SQLAlchemyRepositories


def main() -> None:
    """中文：该函数或方法负责“执行当前模块的命令行入口”相关处理。

    English: Create schema and idempotently seed a local demo tenant and source.
    """

    # 中文：变量 `parser` 用于保存“解析器”相关数据；其精确定义与约束见下方英文说明。
    # English: Command-line parser keeps demo seed values explicit.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", default=None)
    parser.add_argument("--tenant-name", default="Development Tenant")
    parser.add_argument("--source-name", default="General Knowledge")
    parser.add_argument(
        "--content-profile",
        choices=tuple(profile.value for profile in ContentProfile),
        default=ContentProfile.GENERAL_PROSE.value,
        help="Source content profile selecting the V0.3 adaptive chunk strategy.",
    )
    # 中文：变量 `arguments` 用于保存“`arguments`”相关数据；其精确定义与约束见下方英文说明。
    # English: Parsed arguments determine only development seed metadata.
    arguments = parser.parse_args()
    settings = default_settings()
    container = build_container(settings)
    tenant_id = arguments.tenant_id or settings.security.default_tenant_id
    source_id = stable_id("src", (tenant_id, arguments.source_name))
    with transactional_session(container.sessions) as session:
        # 中文：变量 `tenant` 用于保存“租户”相关数据；其精确定义与约束见下方英文说明。
        # English: Existing tenant makes this script safe to rerun.
        tenant = session.get(TenantRow, tenant_id)
        if tenant is None:
            session.add(TenantRow(id=tenant_id, name=arguments.tenant_name, is_active=True))
            session.flush()
        repositories = SQLAlchemyRepositories(session)
        if repositories.get_source(tenant_id, source_id) is None:
            repositories.add_source(
                Source(
                    id=source_id,
                    tenant_id=tenant_id,
                    name=arguments.source_name,
                    description="General enterprise policies, procedures, and reference documents.",
                    content_profile=ContentProfile(arguments.content_profile),
                    visibility=SourceVisibility.TENANT,
                )
            )
    print(f"Initialized tenant={tenant_id} source={source_id}")


if __name__ == "__main__":
    main()
