"""中文：本模块负责实现“追踪”相关功能。

English: Expose redacted trace views after tenant and owner authorization.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from enterprise_rag.api.dependencies import AppContainer, get_container, get_user_context
from enterprise_rag.api.schemas import TraceSchema
from enterprise_rag.domain.models import UserContext

# 中文：变量 `router` 用于保存“路由器”相关数据；其精确定义与约束见下方英文说明。
# English: Router prefix is combined with the application API prefix.
router = APIRouter(prefix="/traces", tags=["traces"])


@router.get("/{trace_id}", response_model=TraceSchema)
def get_trace(
    trace_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    user: Annotated[UserContext, Depends(get_user_context)],
) -> TraceSchema:
    """中文：该函数或方法负责“获取追踪”相关处理。

    English: Return a trace only to its requesting user or a tenant administrator.
    """

    result = container.traces.get(user, trace_id)
    return TraceSchema(
        trace_id=result.trace_id,
        status=result.status,
        steps=list(result.steps),
        metrics=result.metrics,
    )
