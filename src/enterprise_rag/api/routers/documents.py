"""中文：本模块负责实现“文档”相关功能。

English: Expose document upload, detail, deletion, and ingestion-retry use cases.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from enterprise_rag.api.dependencies import AppContainer, get_container, get_user_context
from enterprise_rag.api.schemas import (
    DocumentDetailSchema,
    IndexBuildResponse,
    IngestionAcceptedSchema,
)
from enterprise_rag.domain.models import UserContext
from enterprise_rag.domain.requests import (
    CreateDocumentCommand,
    ReprocessDocumentCommand,
    RetryIngestionCommand,
)

# 中文：变量 `router` 用于保存“路由器”相关数据；其精确定义与约束见下方英文说明。
# English: Router prefix is combined with the application API prefix.
router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "",
    response_model=IngestionAcceptedSchema,
    status_code=status.HTTP_202_ACCEPTED,
)
def upload_document(
    source_id: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    container: Annotated[AppContainer, Depends(get_container)],
    user: Annotated[UserContext, Depends(get_user_context)],
    title: Annotated[str | None, Form()] = None,
) -> IngestionAcceptedSchema:
    """中文：该函数或方法负责“上传文档”相关处理。

    English: Apply the second file-level size defense, copy bytes, and enqueue ingestion.
    """

    # 中文：变量 `suffix` 用于保存“`suffix`”相关数据；其精确定义与约束见下方英文说明。
    # English: Suffix is cosmetic; UploadValidator rechecks extension and binary signature.
    suffix = Path(file.filename or "upload.bin").suffix[:16]
    # 中文：变量 `temporary_path` 用于保存“`temporary``path`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Delete=False keeps bytes available while the synchronous service stores them.
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix="enterprise-rag-upload-",
            suffix=suffix,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            # 中文：关键变量 `received_bytes` 是 ASGI 请求体中间件之后的第二道文件级防线。
            # English: Key variable `received_bytes` is the second file-level defense after
            # the ASGI request-body middleware.
            received_bytes = 0
            maximum_bytes = container.settings.ingestion.max_file_size_mb * 1024 * 1024
            while data := file.file.read(1024 * 1024):
                received_bytes += len(data)
                if received_bytes > maximum_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=(
                            "Upload exceeds the configured "
                            f"{container.settings.ingestion.max_file_size_mb} MiB limit."
                        ),
                    )
                temporary.write(data)
        result = container.ingestion.create_document(
            CreateDocumentCommand(
                user=user,
                source_id=source_id,
                filename=file.filename or "upload.bin",
                temporary_path=temporary_path,
                title=title,
            )
        )
        return IngestionAcceptedSchema(
            document_id=result.document_id,
            document_version_id=result.document_version_id,
            job_id=result.job_id,
            status=result.status,
        )
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


@router.get("/{document_id}", response_model=DocumentDetailSchema)
def document_detail(
    document_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    user: Annotated[UserContext, Depends(get_user_context)],
) -> DocumentDetailSchema:
    """中文：该函数或方法负责“文档详情”相关处理。

    English: Return permission-safe document lifecycle information.
    """

    result = container.knowledge.document_detail(user, document_id)
    return DocumentDetailSchema(
        document_id=result.document_id,
        source_id=result.source_id,
        title=result.title,
        status=result.status,
        active_version_id=result.active_version_id,
        error_code=result.error_code,
        content_profile=result.content_profile,
        chunk_strategy_version=result.chunk_strategy_version,
        quality_metrics=result.quality_metrics,
    )


@router.delete("/{document_id}", response_model=IndexBuildResponse)
def delete_document(
    document_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    user: Annotated[UserContext, Depends(get_user_context)],
) -> IndexBuildResponse:
    """中文：该函数或方法负责“删除文档”相关处理。

    English: Exclude a document immediately and rebuild the active immutable snapshot.
    """

    result = container.knowledge.delete_document(user, document_id)
    return IndexBuildResponse(
        index_version_id=result.index_version_id,
        chunk_count=result.chunk_count,
        activated=result.activated,
        previous_index_version_id=result.previous_index_version_id,
    )


@router.post(
    "/{document_id}/retry",
    response_model=IngestionAcceptedSchema,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_ingestion(
    document_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    user: Annotated[UserContext, Depends(get_user_context)],
) -> IngestionAcceptedSchema:
    """中文：该函数或方法负责“重试资料接入”相关处理。

    English: Enqueue a fresh durable attempt for a failed document.
    """

    result = container.ingestion.retry(RetryIngestionCommand(user=user, document_id=document_id))
    return IngestionAcceptedSchema(
        document_id=result.document_id,
        document_version_id=result.document_version_id,
        job_id=result.job_id,
        status=result.status,
    )


@router.post(
    "/{document_id}/reprocess",
    response_model=IngestionAcceptedSchema,
    status_code=status.HTTP_202_ACCEPTED,
)
def reprocess_document(
    document_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    user: Annotated[UserContext, Depends(get_user_context)],
) -> IngestionAcceptedSchema:
    """中文：使用资料源当前内容画像对已有原始文件创建新的处理版本。

    English: Create a new processing version using the source's current content profile.
    """

    # 中文：变量 `result` 包含可由 Worker 恢复执行的新持久化任务标识。
    # English: Result contains a new durable job identity recoverable by the worker.
    result = container.ingestion.reprocess(
        ReprocessDocumentCommand(user=user, document_id=document_id)
    )
    return IngestionAcceptedSchema(
        document_id=result.document_id,
        document_version_id=result.document_version_id,
        job_id=result.job_id,
        status=result.status,
    )
