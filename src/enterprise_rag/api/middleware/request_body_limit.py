"""中文：本模块在 multipart 解析前限制完整 HTTP 请求体并稳定返回 413。

English: Limit complete HTTP request bodies before multipart parsing and return stable 413
responses.
"""

from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestBodyTooLarge(Exception):
    """中文：表示流式接收期间累计请求体超过配置上限。

    English: Signal that a streamed request body exceeded the configured limit.
    """


class RequestBodyLimitMiddleware:
    """中文：通过 Content-Length 预检和 receive 计数实施双重请求体限制。

    English: Enforce body limits with both Content-Length preflight and receive counting.
    """

    def __init__(self, app: ASGIApp, maximum_bytes: int) -> None:
        """中文：保存下游 ASGI 应用与正数最大请求字节数。

        English: Store the downstream ASGI application and positive maximum byte count.
        """

        if maximum_bytes < 1:
            raise ValueError("maximum request body bytes must be positive")
        # 中文：关键变量 `_app` 是仅在请求未超限时调用的下游应用。
        # English: Key variable `_app` is called only while the request remains within bounds.
        self._app = app
        # 中文：关键变量 `_maximum_bytes` 同时约束头部声明值和实际流式字节。
        # English: Key variable `_maximum_bytes` limits both declared and streamed sizes.
        self._maximum_bytes = maximum_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """中文：在下游解析前检查并累计一个 HTTP 请求的全部 body 字节。

        English: Preflight and count every body byte before downstream request parsing.
        """

        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        content_length = self._content_length(scope)
        if content_length is not None and content_length > self._maximum_bytes:
            await self._send_too_large(scope, receive, send)
            return

        # 中文：关键变量 `received_bytes` 统计无 Content-Length 或分块传输的真实字节数。
        # English: Key variable `received_bytes` counts real bytes for absent or chunked lengths.
        received_bytes = 0
        response_started = False

        async def limited_receive() -> Message:
            """中文：包装 ASGI receive，并在消息交给 multipart 解析器前执行硬上限。

            English: Wrap ASGI receive and enforce the hard limit before multipart parsing.
            """

            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self._maximum_bytes:
                    raise RequestBodyTooLarge
            return message

        async def tracking_send(message: Message) -> None:
            """中文：跟踪响应是否已经开始，避免超限时发送第二组响应头。

            English: Track response start so an overflow never sends duplicate headers.
            """

            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self._app(scope, limited_receive, tracking_send)
        except RequestBodyTooLarge:
            if response_started:
                raise
            await self._send_too_large(scope, receive, send)

    def _content_length(self, scope: Scope) -> int | None:
        """中文：解析可信格式的非负 Content-Length；缺失或非法时交给流式计数。

        English: Parse a valid non-negative Content-Length or defer to streamed counting.
        """

        for name, value in scope.get("headers", ()):
            if name.lower() != b"content-length":
                continue
            try:
                parsed = int(value.decode("ascii"))
            except (UnicodeDecodeError, ValueError):
                return None
            return parsed if parsed >= 0 else None
        return None

    @staticmethod
    async def _send_too_large(scope: Scope, receive: Receive, send: Send) -> None:
        """中文：返回不泄漏内部路径或配置细节的稳定 413 JSON 响应。

        English: Return a stable 413 JSON response without internal paths or configuration.
        """

        response = JSONResponse(
            status_code=413,
            content={
                "error": {
                    "code": "REQUEST_BODY_TOO_LARGE",
                    "category": "validation",
                    "message": "The request body exceeds the configured size limit.",
                }
            },
        )
        await response(scope, receive, send)
