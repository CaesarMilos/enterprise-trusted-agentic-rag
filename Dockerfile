# 中文：固定 Python 补丁版本；生产发布可在 CI 中进一步替换为已批准的镜像 digest。
# English: Pin the Python patch release; CI may additionally substitute an approved digest.
FROM python:3.11.13-slim-bookworm

# 中文：运行时禁止字节码、强制无缓冲日志，并把缓存放到非 root 可写目录。
# English: Disable bytecode, flush logs, and place caches in a non-root writable directory.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    XDG_CACHE_HOME=/app/.cache \
    PATH=/app/.venv/bin:$PATH

WORKDIR /app

# 中文：OCR 二进制与中文字体版本随 Debian Bookworm 仓库快照解析。
# English: OCR binaries and CJK fonts resolve from the Debian Bookworm repository snapshot.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       fonts-noto-cjk \
       tesseract-ocr \
       tesseract-ocr-chi-sim \
       tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install uv==0.11.33

# 中文：锁文件中的哈希与版本是镜像依赖的唯一来源，禁止构建时解析“最新版本”。
# English: The hash-bearing lockfile is the only dependency source; no latest-version resolution.
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --extra local-models --extra ocr --no-editable

COPY configs ./configs
COPY scripts ./scripts
RUN mkdir -p /app/data /app/.cache \
    && groupadd --gid 10001 rag \
    && useradd --uid 10001 --gid rag --no-create-home --shell /usr/sbin/nologin rag \
    && chown -R rag:rag /app/data /app/.cache

USER 10001:10001

# 中文：健康检查只访问无需认证的就绪端点，不泄露业务或租户数据。
# English: Health check uses an unauthenticated readiness endpoint without tenant data.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/ready', timeout=3)" || exit 1

CMD ["uvicorn", "enterprise_rag.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
