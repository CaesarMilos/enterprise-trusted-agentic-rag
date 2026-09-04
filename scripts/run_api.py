"""中文：以统一的项目环境启动本地 FastAPI 服务。

English: Start the local FastAPI service with the shared project environment.
"""

from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    """中文：默认绑定 127.0.0.1，避免 localhost 代理和 DNS 差异。

    English: Bind to 127.0.0.1 by default to avoid localhost proxy and DNS differences.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    arguments = parser.parse_args()
    uvicorn.run(
        "enterprise_rag.api.main:app",
        host=arguments.host,
        port=arguments.port,
        reload=arguments.reload,
    )


if __name__ == "__main__":
    main()
