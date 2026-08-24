"""中文：构建可注入依赖的 FastAPI 应用、错误映射、中间件和版本化路由。

English: Build an injectable FastAPI application with error mapping, middleware, and
versioned routers.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from enterprise_rag import __version__
from enterprise_rag.api.dependencies import AppContainer, build_container
from enterprise_rag.api.middleware import RequestBodyLimitMiddleware
from enterprise_rag.api.routers import chat, documents, health, indexes, sources, traces
from enterprise_rag.core.enums import ErrorCategory
from enterprise_rag.core.exceptions import EnterpriseRAGError

# 中文：关键映射把稳定领域错误类别转换为稳定 HTTP 状态码。
# English: Key mapping converts stable domain error categories into stable HTTP statuses.
_HTTP_STATUS_BY_CATEGORY = {
    ErrorCategory.VALIDATION: 422,
    ErrorCategory.NOT_FOUND: 404,
    ErrorCategory.PERMISSION: 403,
    ErrorCategory.CONFLICT: 409,
    ErrorCategory.TIMEOUT: 504,
    ErrorCategory.STORAGE: 503,
    ErrorCategory.PARSING: 422,
    ErrorCategory.INDEX: 503,
    ErrorCategory.RETRIEVAL: 503,
    ErrorCategory.MODEL: 503,
    ErrorCategory.INTERNAL: 500,
}


def create_app(container: AppContainer | None = None) -> FastAPI:
    """中文：创建完整应用，并允许测试注入隔离的依赖容器。

    English: Create the complete application while allowing tests to inject an isolated
    dependency container.
    """

    # 中文：关键变量 `resolved_container` 确保每个应用实例只使用一套依赖和设置。
    # English: Key variable `resolved_container` pins one dependency graph and settings set
    # to each application instance.
    resolved_container = container or build_container()
    application = FastAPI(
        title="Enterprise Trusted Agentic RAG",
        version=__version__,
        debug=resolved_container.settings.application.debug,
    )
    # 中文：请求体限制在 multipart 解析和 UploadFile 创建之前执行。
    # English: The body limit runs before multipart parsing and UploadFile creation.
    application.add_middleware(
        RequestBodyLimitMiddleware,
        maximum_bytes=(
            resolved_container.settings.ingestion.max_request_body_size_mb * 1024 * 1024
        ),
    )
    # 中文：应用状态保存唯一容器，路由通过请求依赖读取它。
    # English: Application state holds the sole container retrieved by request dependencies.
    application.state.container = resolved_container

    @application.exception_handler(EnterpriseRAGError)
    async def handle_enterprise_error(
        _: Request,
        exc: EnterpriseRAGError,
    ) -> JSONResponse:
        """中文：把安全的结构化领域异常转换成稳定 JSON 错误信封。

        English: Convert a safe structured domain exception into a stable JSON envelope.
        """

        return JSONResponse(
            status_code=_HTTP_STATUS_BY_CATEGORY.get(exc.detail.category, 500),
            content={
                "error": {
                    "code": exc.detail.code,
                    "category": exc.detail.category.value,
                    "message": exc.detail.message,
                    "context": exc.detail.context,
                }
            },
        )

    # 中文：关键变量 `api_prefix` 让所有业务路由共享经过校验的版本前缀。
    # English: Key variable `api_prefix` gives every business router one validated version
    # prefix.
    api_prefix = resolved_container.settings.application.api_prefix
    application.include_router(chat.router, prefix=api_prefix)
    application.include_router(documents.router, prefix=api_prefix)
    application.include_router(sources.router, prefix=api_prefix)
    application.include_router(indexes.router, prefix=api_prefix)
    application.include_router(traces.router, prefix=api_prefix)
    application.include_router(health.router, prefix=api_prefix)
    return application
