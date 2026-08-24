"""中文：本模块负责实现“索引”相关功能。

English: Expose administrator index listing and immutable rebuild endpoints.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from enterprise_rag.api.dependencies import AppContainer, get_container, get_user_context
from enterprise_rag.api.schemas import IndexBuildResponse, IndexSchema
from enterprise_rag.core.enums import ErrorCategory
from enterprise_rag.core.exceptions import PermissionDeniedError, error_detail
from enterprise_rag.domain.models import UserContext

# 中文：变量 `router` 用于保存“路由器”相关数据；其精确定义与约束见下方英文说明。
# English: Router prefix is combined with the application API prefix.
router = APIRouter(prefix="/indexes", tags=["indexes"])


@router.get("", response_model=list[IndexSchema])
def list_indexes(
    container: Annotated[AppContainer, Depends(get_container)],
    user: Annotated[UserContext, Depends(get_user_context)],
) -> list[IndexSchema]:
    """中文：该函数或方法负责“列出索引”相关处理。

    English: Return immutable index history to tenant administrators.
    """

    return [IndexSchema.model_validate(item) for item in container.knowledge.list_indexes(user)]


@router.post("/rebuild", response_model=IndexBuildResponse)
def rebuild_index(
    container: Annotated[AppContainer, Depends(get_container)],
    user: Annotated[UserContext, Depends(get_user_context)],
) -> IndexBuildResponse:
    """中文：该函数或方法负责“重建索引”相关处理。

    English: Build, validate, publish, and activate a new snapshot from READY documents.
    """

    if not user.is_admin():
        raise PermissionDeniedError(
            error_detail(
                "INDEX_REBUILD_DENIED",
                ErrorCategory.PERMISSION,
                "Only tenant administrators may rebuild indexes.",
            )
        )
    result = container.indexes.rebuild_active(user.tenant_id)
    return IndexBuildResponse(
        index_version_id=result.index_version_id,
        chunk_count=result.chunk_count,
        activated=result.activated,
        previous_index_version_id=result.previous_index_version_id,
    )
