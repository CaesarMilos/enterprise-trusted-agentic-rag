"""中文：本模块负责实现“资料源”相关功能。

English: Expose knowledge sources visible to the trusted caller.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from enterprise_rag.api.dependencies import AppContainer, get_container, get_user_context
from enterprise_rag.api.schemas import SourceProfileUpdateSchema, SourceSchema
from enterprise_rag.domain.models import UserContext

# 中文：变量 `router` 用于保存“路由器”相关数据；其精确定义与约束见下方英文说明。
# English: Router prefix is combined with the application API prefix.
router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("", response_model=list[SourceSchema])
def list_sources(
    container: Annotated[AppContainer, Depends(get_container)],
    user: Annotated[UserContext, Depends(get_user_context)],
) -> list[SourceSchema]:
    """中文：该函数或方法负责“列出资料源”相关处理。

    English: Return active sources after tenant, visibility, group, and explicit-grant
    filtering.
    """

    return [SourceSchema.model_validate(item) for item in container.knowledge.list_sources(user)]


@router.patch("/{source_id}/content-profile", response_model=SourceSchema)
def update_source_content_profile(
    source_id: str,
    payload: SourceProfileUpdateSchema,
    container: Annotated[AppContainer, Depends(get_container)],
    user: Annotated[UserContext, Depends(get_user_context)],
) -> SourceSchema:
    """中文：更新资料源内容画像，并明确提示已有文档需要重新处理。

    English: Update a source content profile and signal that existing documents need reprocessing.
    """

    # 中文：变量 `result` 来自租户隔离且仅管理员可调用的知识服务。
    # English: Result comes from the tenant-isolated administrator-only knowledge service.
    result = container.knowledge.update_source_content_profile(
        user,
        source_id,
        payload.content_profile,
        payload.chunk_strategy_override,
    )
    return SourceSchema.model_validate(result)
