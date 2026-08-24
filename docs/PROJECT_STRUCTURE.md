# 工程结构说明

本工程采用分层单体架构。第一版在一台个人电脑上完整运行，但核心接口为后续替换数据库、模型和索引实现保留边界。

| 目录 | 职责 |
|---|---|
| `configs/` | 默认、开发和评估配置 |
| `src/enterprise_rag/core/` | 配置、枚举、异常、ID 与日志 |
| `src/enterprise_rag/domain/` | 稳定领域模型、请求、结果与协议 |
| `src/enterprise_rag/ingestion/` | 文件校验、PDF/OCR 分流、结构恢复、内容画像策略与质量检查 |
| `src/enterprise_rag/indexing/` | Embedding、FAISS、BM25 与索引版本发布 |
| `src/enterprise_rag/retrieval/` | 权限过滤、资料源路由、混合检索、重排与动态 Top-K |
| `src/enterprise_rag/agent/` | 显式 Python 状态机、证据评分、重检索、回答与引用校验 |
| `src/enterprise_rag/services/` | 文档接入、知识管理、问答与 Trace 用例 |
| `src/enterprise_rag/infrastructure/` | LLM、数据库和文件存储的具体适配器 |
| `src/enterprise_rag/observability/` | Trace、指标与模型成本记录 |
| `src/enterprise_rag/evaluation/` | 检索、回答、引用与拒答评估 |
| `src/enterprise_rag/api/` | FastAPI 应用、依赖和路由 |
| `src/enterprise_rag/ui/` | Streamlit 用户页与管理页 |
| `scripts/` | 初始化、批量接入、重建索引和评估脚本 |
| `tests/` | 单元、集成、端到端测试及小型自有测试资料 |
| `data/` | 上传文件、索引、Trace 和本地数据库运行数据 |
| `reports/` | 评估结果、消融实验、图表和项目报告 |

## 依赖方向

```text
API / UI
  → Services
    → Agent / Retrieval / Ingestion / Indexing
      → Domain protocols
        ← Infrastructure implementations
```

领域层不得依赖 FastAPI、SQLAlchemy、FAISS 或具体模型 SDK。API 不得越过 Service 直接调用数据库、检索器或 LLM。

## 在线问答依赖

```text
POST /chat
→ ChatService 固定 UserContext、RetrievalScope、ACTIVE index_version
→ AgentOrchestrator
→ HybridRetriever
→ SourceRouter
→ Dense + BM25 并行召回
→ RRF
→ 可选 Cross-encoder
→ DynamicTopK
→ ContextBuilder
→ EvidenceGrader
→ 最多两次 Query Rewrite
→ AnswerGenerator
→ CitationVerifier
→ AnswerResult / RefusalResult
```

## 资料接入依赖

```text
POST /documents
→ UploadValidator
→ LocalFileStore
→ Document + DocumentVersion + IngestionJob
→ Worker 租约领取
→ Loader / Cleaner / StructureParser / DynamicSemanticChunker
→ Chunk 持久化
→ 统一 IndexBuildPlan
→ FAISS + BM25 + SourceCatalog 写入 Staging
→ Manifest 与重新加载校验
→ 原子发布目录
→ 事务切换 ACTIVE + Document READY + Job SUCCEEDED
```
