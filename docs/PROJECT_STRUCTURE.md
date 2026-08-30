# V4 工程结构与源码职责

## 顶层文件

| 路径 | 职责 |
|---|---|
| `pyproject.toml` / `uv.lock` | Python 版本、依赖、严格静态检查和可复现锁定 |
| `configs/*.yaml` | 默认、开发、评测配置；环境变量可做嵌套覆盖 |
| `Dockerfile` | 锁依赖、OCR/本地模型可选项、非 root 运行和健康检查 |
| `docker-compose.yml` | JWT 生产拓扑，只有网关对外暴露 |
| `compose.dev.yml` | 只绑定回环地址的开发拓扑 |
| `deploy/nginx.conf` | 请求体限制、身份头清洗和 API 反向代理 |
| `scripts/` | 初始化、Worker、批量接入、索引维护、评测和报告比较 |

## `core/` 与 `domain/`

| 源文件 | 核心类/函数 | 功能与算法 |
|---|---|---|
| `core/config.py` | `Settings`、`load_settings` | 深合并 YAML/环境变量，冻结配置；校验 Chunk 范围、权重和认证互斥 |
| `core/deadline.py` | `DeadlineBudget` | 单调时钟全局截止、子调用剩余预算、节点前后硬检查 |
| `core/enums.py` | 生命周期、画像、认证枚举 | 稳定的数据库/API 状态词汇 |
| `core/exceptions.py` | 领域异常、`error_detail` | 区分校验、权限、租约、取消、生命周期、索引、模型和超时 |
| `core/ids.py` | `stable_id`、`stable_chunk_id` | 内容哈希与规范字段组合的确定性身份 |
| `core/state_machine.py` | `ensure_transition` | 文档、任务和索引合法迁移检查 |
| `core/logging.py` | `RedactionFilter`、`JsonFormatter` | JSON 日志和敏感字段脱敏 |
| `domain/models.py` | `Document`、`DocumentVersion`、`Chunk`、`IngestionJob`、`JobFence`、`IndexVersion` | 不可变版本、generation fencing、父子 Chunk、任务租约和索引快照 |
| `domain/requests.py` / `results.py` | 用例命令与返回对象 | 将服务层与 FastAPI/Pydantic 解耦 |
| `domain/protocols/*.py` | Repository、Index、Model、Storage、Trace 协议 | 依赖倒置和可测试适配器边界 |

## `ingestion/`

| 源文件 | 核心类/函数 | 功能与算法 |
|---|---|---|
| `validator.py` | `UploadValidator` | 扩展名、大小、文件签名和 SHA-256 校验 |
| `loader_registry.py` | `LoaderRegistry` | 按已验证文件类型选择唯一 Loader |
| `loaders/pdf_loader.py` | `PDFLoader` | 逐页文本层读取、混合 PDF 缺页 OCR 和质量拒绝 |
| `loaders/markdown_loader.py` | `MarkdownLoader` | 保留标题、代码和表格块 |
| `loaders/text_loader.py` | `TextLoader` | 编码检测/校验与文本块生成 |
| `ocr.py` | `OCRProvider` | OCR 端口及结果模型 |
| `pdf_reflow.py` | `PDFTextReflow` | 页眉页脚统计去除、断行与孤立标点修复 |
| `cleaner.py` | `TextCleaner` | Unicode/空白规范化和清洗统计 |
| `metadata_extractor.py` | `MetadataExtractor` | 文档标题、页码和解析质量元数据 |
| `chunking/content_profiler.py` | `ContentProfiler` | 确定性结构信号评分与低置信度回退 |
| `structure_parser.py` | `StructureParser`、`estimate_tokens` | 标题、条款、列表、表格、代码、句子和偏移量结构树 |
| `chunking/chinese_sentence_splitter.py` | `ChineseSentenceSplitter` | 保护 URL/小数/版本号/括号引号的中文安全切句 |
| `chunking/boundary_scorer.py` | `AdaptiveBoundaryScorer` | 五特征加权分数和按 Token 长度变化的动态阈值 |
| `boundary_analyzer.py` | `EmbeddingSimilarity`、`LLMBoundaryJudge`、`AdaptiveBoundaryAnalyzer` | 硬边界优先、批量向量、质心连续性、模糊区 LLM 和确定性回退 |
| `chunk_strategies.py` | `ProfileChunkStrategy`、`ChunkStrategyRegistry` | 六种内容画像的规则、参数和策略选择 |
| `semantic_chunker.py` | `DynamicSemanticChunker` | 长单元安全拆分、短块受约束合并、完整句重叠、稳定 ID 和 Parent 聚合 |
| `quality_validator.py` | `ChunkQualityValidator` | 空/超长/重复/碎片/页码/父子完整性发布门禁 |
| `pipeline.py` | `IngestionPipeline` | 串联加载、清洗、画像、结构、切块、质量和版本快照一致性校验 |

## `indexing/` 与 `retrieval/`

| 源文件 | 核心类/函数 | 功能与算法 |
|---|---|---|
| `indexing/models.py` | `IndexBuildPlan.from_domain` | 只将叶子 Chunk 规范化成一个不可变构建计划 |
| `indexing/embedding_service.py` | `EmbeddingService` | 批量向量、维度/有限值/零范数校验 |
| `indexing/vector_index.py` | `FaissVectorIndex` | 归一化向量与内积余弦 Top-K |
| `indexing/bm25_index.py` | `lexical_tokens`、`PersistentBM25Index` | 中文字符/二元词组、英文词、条款锚点和 BM25 |
| `indexing/source_catalog.py` | `PersistentSourceCatalog` | Source 路由画像与关键词目录 |
| `indexing/index_manifest.py` | `create/load/verify_manifest` | 文件哈希、模型/配置指纹和快照完整性 |
| `indexing/index_coordinator.py` | `IndexCoordinator` | Staging 构建、重新加载验证、原子目录发布 |
| `retrieval/source_router.py` | `SourceRouter` | 授权候选内的确定性 Source 路由与弱匹配回退 |
| `retrieval/query_normalizer.py` / `identifier_normalizer.py` | 查询和编号规范化 | 法规条号、章节号、中英文编号的精确锚点 |
| `retrieval/dense_retriever.py` / `bm25_retriever.py` | 双路 Retriever | 独立召回并保持故障可降级 |
| `retrieval/fusion.py` | `ReciprocalRankFusion` | RRF 融合、Parent 家族去重和元数据合并 |
| `retrieval/reranker.py` | `CandidateReranker` | Query、标题路径、编号、Child 正文的可选重排 |
| `retrieval/dynamic_top_k.py` | `DynamicTopK` | 分数断层、Parent 去重、文档多样性和 Token 预算选择 |
| `retrieval/parent_expander.py` | `ParentExpander` | 同租户/文档/版本验证后的 Parent 上下文扩展 |
| `retrieval/context_builder.py` | `ContextBuilder` | Parent 正文作为上下文、Child 身份作为引用 |
| `retrieval/hybrid_retriever.py` | `HybridRetriever` | 并发双路召回、降级、融合、重排、Top-K 和扩展总协调 |

## `services/`、`agent/` 与 `security/`

| 源文件 | 核心类/函数 | 功能与算法 |
|---|---|---|
| `services/ingestion_service.py` | `IngestionService` | 上传、重试、重处理和策略快照；任务冻结 generation |
| `services/job_lease_guard.py` | `JobLeaseGuard` | 长任务心跳续租和失租传播 |
| `services/ingestion_worker.py` | `IngestionWorker` | claim、解析、切块、fence 检查、写入、索引发布和状态收口 |
| `services/knowledge_service.py` | `IndexBuildService`、`KnowledgeService` | 统一候选发布、CAS、删除 fencing、Source/文档/索引管理 |
| `services/chat_service.py` | `ChatService` | 请求固定活动索引、ACL 范围、状态机和 Trace 生命周期 |
| `services/trace_service.py` | `TraceService` | 发起者/租户管理员可见的脱敏 Trace |
| `agent/orchestrator.py` | `AgentOrchestrator.run` | 有界检索、评分、最多两次改写、回答、引用或拒答 |
| `agent/evidence_grader.py` | `EvidenceGrader` | 覆盖度、冲突和最低证据规则 |
| `agent/query_rewriter.py` | `QueryRewriter` | 保留原问题、防重复和语义漂移的受预算改写 |
| `agent/answer_generator.py` | `AnswerGenerator` | 仅基于 Evidence Pack 的引用式生成 |
| `agent/citation_verifier.py` | `CitationVerifier` | Chunk 存在性、ACL、版本、定位和声明支持校验 |
| `agent/model_invocation.py` | `complete_with_timeout` | 向支持的提供方传递剩余硬超时并兼容测试适配器 |
| `security/jwt_auth.py` | `decode_hs256_user_context` | HS256 签名、时效、issuer/audience 和租户声明验证 |
| `security/startup.py` | `validate_security_startup` | 生产 Demo 禁用及密钥缺失时 fail-closed |

## `infrastructure/`、`api/` 与其他模块

| 目录/源文件 | 主要职责 |
|---|---|
| `infrastructure/persistence/database.py` | 引擎、会话、表初始化和幂等 V4 SQLite 列迁移 |
| `infrastructure/persistence/orm_models.py` | 全部 SQLAlchemy 表结构 |
| `infrastructure/persistence/repositories.py` | 租户过滤 CRUD、原子 claim/续租/fence、删除请求和索引 CAS |
| `infrastructure/indexes/index_runtime.py` | 请求固定不可变索引 Bundle 并校验 Manifest |
| `infrastructure/storage/*` | 租户隔离原文件、路径安全、原子落盘和清理 |
| `infrastructure/embeddings/*` | 本地和 OpenAI-compatible 向量适配器 |
| `infrastructure/llm/*` | OpenAI-compatible LLM、超时和安全元数据 |
| `infrastructure/ocr/*` | Tesseract 逐词置信度、行重建和页级结果 |
| `infrastructure/rerankers/*` | Cross-Encoder 重排适配器 |
| `api/dependencies.py` | 配置加载、启动安全校验和全依赖图装配 |
| `api/application.py` / `api/main.py` | FastAPI 工厂、异常处理、中间件和进程入口 |
| `api/routers/*.py` / `api/schemas.py` | 健康、Source、文档、索引、问答、Trace HTTP 边界 |
| `observability/*` | JSONL/数据库 Trace、内存指标、模型费用和脱敏事件 |
| `evaluation/*` | 数据集、路由/检索/引用/答案/拒答/切块指标和基线比较 |
| `ui/streamlit_app.py` | 只通过 HTTP API 使用系统的开发/管理 UI |

每个 Python 源文件都有中英双语模块说明；公共类/函数、关键算法步骤和关键状态变量使用中英双语注释。新增代码必须维持这一约束，并通过文档字符串审计、Ruff、MyPy 和测试门禁。
