"""中文：验证 FastAPI 在 multipart 解析边界前拒绝超限请求体。

English: Verify FastAPI rejects oversized request bodies before the multipart parsing boundary.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, File, UploadFile
from fastapi.testclient import TestClient

from enterprise_rag.api.middleware import RequestBodyLimitMiddleware


def _test_application(maximum_bytes: int) -> FastAPI:
    """中文：创建一个只包含 multipart 上传的最小受限 FastAPI 应用。

    English: Create a minimal body-limited FastAPI application with one multipart upload.
    """

    application = FastAPI()
    application.add_middleware(RequestBodyLimitMiddleware, maximum_bytes=maximum_bytes)

    @application.post("/upload")
    async def upload(file: Annotated[UploadFile, File()]) -> dict[str, int]:
        """中文：返回已经 multipart 解析的文件字节数。

        English: Return the byte count of a file that passed multipart parsing.
        """

        payload = await file.read()
        return {"size": len(payload)}

    return application


def test_oversized_multipart_request_returns_stable_413() -> None:
    """中文：确认完整 multipart 体超限时返回稳定机器错误码。

    English: Ensure an oversized multipart body returns a stable machine-readable 413 code.
    """

    with TestClient(_test_application(256)) as client:
        response = client.post(
            "/upload",
            files={"file": ("manual.txt", b"x" * 1024, "text/plain")},
        )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "REQUEST_BODY_TOO_LARGE"


def test_small_multipart_request_reaches_the_endpoint() -> None:
    """中文：确认正常请求不会被前置限制器误拒。

    English: Ensure a normal request is not rejected by the pre-parser limiter.
    """

    with TestClient(_test_application(4096)) as client:
        response = client.post(
            "/upload",
            files={"file": ("manual.txt", b"safe", "text/plain")},
        )

    assert response.status_code == 200
    assert response.json() == {"size": 4}
