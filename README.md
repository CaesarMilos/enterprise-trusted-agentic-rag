# Enterprise Trusted Agentic RAG

当前版本为 **V0.3.0rc2 可靠性修复候选版**。系统面向企业说明书、技术资料和结构相似的规范/法典文本，支持 PDF、Markdown、TXT；接入时执行 PDF 版式恢复、标题/编号识别、向量语义边界与可选 LLM 模糊边界复核，并生成父子 Chunk。本候选版重点修复了删除撤销、Worker 租约 fencing、索引并发激活、LLM 调用预算和上传边界。

## 已实现的工程边界

- PDF、Markdown、TXT Loader、流式上传硬上限与文件签名校验；
- Source 级 `general_prose`、`manual`、`technical_doc` 内容画像；
- PDF 页眉页脚去除、视觉断行/孤立标点恢复、标题/条款/步骤编号识别；
- “硬结构 → Token → 向量 → 模糊区 LLM → 确定性回退”的自适应切块；
- 父子 Chunk、检索文本与引用正文分离、策略/模型/参数版本冻结；
- 混合 PDF 缺页逐页 OCR 合并；未补齐任何一页都不会发布不完整索引；
- SQLAlchemy + SQLite 文档版本、Chunk、租约任务、索引版本与 Trace 元数据；
- 原文件租户隔离、路径穿越防护、原子保存与 SHA-256；
- 同一 `IndexBuildPlan` 构建 FAISS `IndexFlatIP`、BM25、Source Catalog；
- Staging 写入、Manifest 校验、重新加载验证、不可变发布、事务切换 ACTIVE；
- 中文二元词组、`clause:143` 等精确锚点、弱 Source 路由全范围回退；
- 检索前 ACL、Dense/BM25 独立降级、RRF、父子去重动态 Top-K；
- 显式 Python Agent 状态机，不依赖 LangGraph；
- 最多“首次检索 + 两次改写重检索”，区分拒答、系统错误和超时；
- 引用存在性、权限、版本、定位与基础事实支持校验，并返回最相关局部摘录；
- SQLite 原子任务领取、索引激活乐观并发校验、候选重处理失败保留旧服务；
- 长任务心跳续租、attempt fencing token、失租 Worker 禁止写 Chunk/终态/激活；
- 删除或停用后按数据库生命周期再校验 Chunk，旧活动索引不能继续泄漏证据；
- ASGI 与网关在 multipart 落盘前限制完整请求体，端点再执行单文件二次限制；
- 数据库 Trace 摘要与 JSONL 检索/评估/引用步骤；
- FastAPI、HTTP-only Streamlit、持久 Worker、评估指标、Docker Compose；
- 单元、集成与安全测试骨架及核心算法测试。

## 本地安装

推荐 Python 3.11：

```bash
python -m venv .venv
```

在 Windows PowerShell 中激活：

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,local-models]"
Copy-Item .env.example .env
```

默认开发配置连接本地 OpenAI-compatible 端点 `http://localhost:11434/v1`，模型名为 `qwen3:8b`。可通过 `.env.example` 中的嵌套环境变量切换到 Ollama、OpenAI、百炼或智谱的兼容端点。

若需要自动处理扫描或混合 PDF，再安装 OCR 可选依赖和系统 Tesseract：

```powershell
python -m pip install -e ".[dev,local-models,ocr]"
# 在 .env 中设置：
# ENTERPRISE_RAG__OCR__ENABLED=true
```

默认中文向量模型为 `BAAI/bge-small-zh-v1.5`，首次运行会下载或加载本地缓存。V0.2 的 MiniLM 索引不能与新向量空间混用。

## 初始化与启动

先初始化 Demo Tenant 与 Source：

```bash
python scripts/init_db.py
```

启动三个进程：

```bash
uvicorn enterprise_rag.api.main:app --reload
python scripts/run_worker.py
streamlit run src/enterprise_rag/ui/streamlit_app.py
```

- API 文档：<http://localhost:8000/docs>
- Streamlit：<http://localhost:8501>
- Liveness：<http://localhost:8000/api/v1/health/live>
- Readiness：<http://localhost:8000/api/v1/health/ready>

开发配置启用 Header Demo 身份，默认 `demo-admin / demo-tenant / admin`。生产可启用受共享密钥保护的可信反向代理身份头；未配置真实身份适配器时 API 明确返回 401。

## 从 V0.2 升级

1. 备份 `data/`，保留旧压缩包；不要删除可回滚数据。
2. 用 V0.3 代码启动一次，数据库会幂等增加 `document_versions.ingestion_snapshot`。
3. 在 Admin 中为资料源确认 `content_profile`。
4. 对现有文档执行 reprocess，让新版本使用 V2 切块策略和 BGE 向量。
5. 确认新索引 `ACTIVE`、质量指标和回归问答后，再清理旧索引。

旧活动版本会在候选版本处理期间继续服务；候选失败不会把逻辑文档改成 `FAILED`。

## Docker

```bash
docker compose up --build
```

`api`、`worker` 和 `ui` 共享持久数据卷；UI 只通过 HTTP 调用 API。

## 测试与质量检查

```bash
pytest
ruff check src tests scripts
mypy src
```

核心测试覆盖民法典式条款重排、精确编号锚点、Markdown 标题硬边界、混合 PDF 缺页 OCR、坏 JSON 调用上限、提供方异常回退、删除后旧索引检索、Worker 失租双代次竞争、FastAPI 413、可信代理认证和可选真实 OCR。具体验收状态见 `docs/IMPLEMENTATION_STATUS.md`。

## 关键脚本

```text
scripts/init_db.py             初始化数据库与开发 Source
scripts/ingest_directory.py    通过正式 Service 批量接入目录
scripts/run_worker.py          运行持久任务 Worker
scripts/rebuild_indexes.py     重建并原子发布索引
scripts/cleanup_indexes.py     默认 dry-run 清理历史快照
scripts/recover_indexes.py     校验 Manifest 与可恢复快照
scripts/run_evaluation.py      运行固定评估集
```

详细设计与文件职责见 `docs/`。
