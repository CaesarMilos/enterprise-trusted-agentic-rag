# 中文：使用同一个可复现的 Python 镜像构建 API、工作进程和 Streamlit 界面。
# English: Build the API, worker, and Streamlit UI from one reproducible Python image.
FROM python:3.11-slim

# 中文：禁止生成字节码缓存，并让容器日志立即刷新到标准输出。
# English: Prevent bytecode artifacts and force immediate container log flushing.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# 中文：应用文件及其相对数据路径均位于此目录下。
# English: Application files and relative data paths live beneath this directory.
WORKDIR /app

# 中文：安装真实中文/英文 OCR 引擎和 CJK 字体，保证容器链路可验收。
# English: Install real Chinese/English OCR engines and CJK fonts for container acceptance.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       fonts-noto-cjk \
       tesseract-ocr \
       tesseract-ocr-chi-sim \
       tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# 中文：安装本地包之前，先复制依赖元数据和源码。
# English: Copy dependency metadata and source before installing the local package.
COPY pyproject.toml README.md ./
COPY src ./src

# 中文：local-models 与 ocr 可选依赖提供 FAISS、中文向量模型和逐页 OCR。
# English: Local-model and OCR extras provide FAISS, Chinese embeddings, and page OCR.
RUN python -m pip install --upgrade pip \
    && python -m pip install ".[local-models,ocr]"

# 中文：运行时配置、脚本和空数据挂载点随已安装代码一并复制。
# English: Runtime configuration, scripts, and empty data mount points follow the installed code.
COPY configs ./configs
COPY scripts ./scripts
COPY data ./data

# 中文：镜像默认启动 API；Compose 会为工作进程和界面服务覆盖该命令。
# English: API is the default image process; Compose overrides it for worker and UI services.
CMD ["uvicorn", "enterprise_rag.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
