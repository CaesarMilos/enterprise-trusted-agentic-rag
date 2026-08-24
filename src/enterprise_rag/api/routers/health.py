"""中文：本模块负责实现“健康检查”相关功能。

English: Expose process liveness and database readiness probes.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text

from enterprise_rag import __version__
from enterprise_rag.api.dependencies import AppContainer, get_container
from enterprise_rag.api.schemas import HealthSchema
from enterprise_rag.infrastructure.persistence.database import transactional_session

# 中文：变量 `router` 用于保存“路由器”相关数据；其精确定义与约束见下方英文说明。
# English: Health endpoints live beneath the common API prefix.
router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=HealthSchema)
def live() -> HealthSchema:
    """中文：该函数或方法负责“存活检查”相关处理。

    English: Confirm that the Python process and router are responsive.
    """

    return HealthSchema(status="ok", version=__version__)


@router.get("/ready", response_model=HealthSchema)
def ready(
    container: Annotated[AppContainer, Depends(get_container)],
) -> HealthSchema:
    """中文：该函数或方法负责“就绪”相关处理。

    English: Confirm that durable metadata storage accepts a simple query.
    """

    try:
        with transactional_session(container.sessions) as session:
            session.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        ) from exc
    return HealthSchema(status="ready", version=__version__)
