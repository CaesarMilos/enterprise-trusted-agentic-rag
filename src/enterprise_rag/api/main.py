"""中文：为 Uvicorn 暴露生产 FastAPI 应用，并重新导出无副作用的应用工厂。

English: Expose the production FastAPI application to Uvicorn and re-export the side-effect-free
application factory.
"""

from enterprise_rag.api.application import create_app

# 中文：关键变量 `app` 是 Uvicorn 导入的单一进程级应用实例。
# English: Key variable `app` is the conventional process-wide instance imported by Uvicorn.
app = create_app()
