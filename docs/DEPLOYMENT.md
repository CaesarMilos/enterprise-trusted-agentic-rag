# V4 启动与部署

## 运行要求

- Python `>=3.11,<3.13`；推荐 3.11。
- `uv` 和已提交的 `uv.lock`。
- 本地向量/重排需要 FAISS 与 Sentence Transformers。
- 扫描 PDF 需要 Tesseract、中文/英文语言包、PyMuPDF 和 Pillow。
- 默认开发 LLM 需要提供 OpenAI-compatible `/v1` 接口的 Ollama 或其他服务。

## 本地开发

```bash
uv sync --frozen --extra dev --extra local-models
cp .env.example .env
uv run python scripts/init_db.py --source-name 'General Knowledge'
```

三个终端分别执行：

```bash
ENTERPRISE_RAG_ENV=development uv run uvicorn enterprise_rag.api.main:app --reload
ENTERPRISE_RAG_ENV=development uv run python scripts/run_worker.py
ENTERPRISE_RAG_ENV=development uv run streamlit run src/enterprise_rag/ui/streamlit_app.py
```

Worker 也可单次处理队首任务：

```bash
ENTERPRISE_RAG_ENV=development uv run python scripts/run_worker.py --once
```

## 开发 Compose

```bash
docker compose -f compose.dev.yml up --build
```

API/UI 只绑定 `127.0.0.1`。开发 Compose 使用 Demo Auth，不得部署到公网或共享主机。

## 生产 Compose

```bash
export ENTERPRISE_RAG_JWT_SECRET='a-long-random-secret-from-a-secret-manager'
export LLM_API_KEY='provider-key-if-required'
docker compose up --build -d
docker compose ps
```

生产 Compose 的网关映射端口 `8000`，API 只 `expose` 到内部网络。容器根文件系统只读、使用 UID/GID 10001、删除 capabilities，并把数据库、上传和索引放入持久卷。

当前 Nginx 示例负责身份头清洗和反向代理；互联网部署必须在其前面或内部终止 TLS，并采用组织批准的证书、WAF、速率限制和密钥轮换方案。

## 配置覆盖

配置加载顺序是 `configs/default.yaml`、`configs/${ENTERPRISE_RAG_ENV}.yaml`、`ENTERPRISE_RAG__SECTION__FIELD` 环境变量。环境变量优先，值按 JSON/YAML 标量解析。

常用生产变量：

```text
ENTERPRISE_RAG_ENV=production
ENTERPRISE_RAG__SECURITY__AUTHENTICATION_MODE=jwt
ENTERPRISE_RAG_JWT_SECRET=...
ENTERPRISE_RAG__OCR__ENABLED=true|false
ENTERPRISE_RAG__INGESTION__LLM_BOUNDARY_ENABLED=true|false
ENTERPRISE_RAG__INGESTION__JOB_LEASE_SECONDS=300
ENTERPRISE_RAG__INGESTION__JOB_HEARTBEAT_SECONDS=60
LLM_API_KEY=...
EMBEDDING_API_KEY=...
```

生产认证配置或密钥不完整时，依赖容器会在数据库和监听端口创建前拒绝启动。

## 数据库与持久目录

启动时 `initialize_database` 创建缺失表，并对已有 SQLite 数据库幂等补充 V4 生命周期、取消、版本快照和索引状态列。升级或迁移前必须备份整个 `data/`，并在副本上完成上传、重处理、问答和删除演练。

不可变索引目录包含 Manifest 和构建产物。`cleanup_indexes.py` 默认 dry-run；确认旧快照已退役且无需回滚后再执行清理。`recover_indexes.py` 用于校验可恢复快照。

## 健康与冒烟

```bash
curl -fsS http://127.0.0.1:8000/api/v1/health/live
curl -fsS http://127.0.0.1:8000/api/v1/health/ready
```

发布冒烟必须覆盖：创建资料源、上传三种文件、Worker 完成、文档 `READY`、索引 `ACTIVE`、问答带引用、无答案拒答、删除后检索不可见，以及重启 API/Worker 后状态不污染。

## 发布门禁

```bash
uv lock --check
uv run ruff check src tests scripts
uv run mypy src
uv run pytest
uv pip check --python .venv/bin/python
docker build .
docker compose config
```

还要在目标环境执行真实 OCR、Embedding、Reranker、LLM 和固定评测集。只有代码门禁、容器闭环、安全竞态和准确率门禁全部通过，候选镜像才可发布。
