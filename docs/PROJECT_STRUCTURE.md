# 工程结构 / Project structure

```text
enterprise-trusted-agentic-rag/
├── alembic.ini
├── migrations/
│   ├── env.py
│   └── versions/
│       ├── 0001_v4_baseline.py
│       └── 0002_v5_correctness_contracts.py
├── configs/
│   ├── default.yaml
│   ├── development.yaml
│   └── evaluation.yaml
├── scripts/
│   ├── bootstrap_dev.py
│   ├── run_api.py
│   ├── run_worker.py
│   ├── run_ui.py
│   ├── run_all_dev.py
│   ├── run_evaluation.py
│   └── cleanup/rebuild/recovery utilities
├── src/enterprise_rag/
│   ├── agent/
│   │   ├── question_planner.py
│   │   ├── evidence_grader.py
│   │   ├── query_rewriter.py
│   │   ├── answer_generator.py
│   │   ├── answer_protocol.py
│   │   ├── citation_verifier.py
│   │   └── orchestrator.py
│   ├── core/
│   │   ├── config.py
│   │   ├── concurrency.py
│   │   ├── deadline.py
│   │   ├── enums.py
│   │   ├── exceptions.py
│   │   └── state_machine.py
│   ├── domain/
│   │   ├── content.py
│   │   ├── locators.py
│   │   ├── questions.py
│   │   ├── evidence.py
│   │   ├── answers.py
│   │   ├── snapshots.py
│   │   ├── quality.py
│   │   ├── provenance.py
│   │   └── publication.py
│   ├── ingestion/
│   │   ├── loaders/
│   │   ├── normalization.py
│   │   ├── boundary_analyzer.py
│   │   ├── semantic_chunker.py
│   │   ├── quality_validator.py
│   │   └── pipeline.py
│   ├── retrieval/
│   │   ├── hybrid_retriever.py
│   │   ├── dynamic_top_k.py
│   │   ├── parent_expander.py
│   │   ├── source_router.py
│   │   ├── fusion.py
│   │   └── models.py
│   ├── infrastructure/
│   │   ├── embeddings/
│   │   ├── indexes/
│   │   ├── llm/
│   │   ├── ocr/
│   │   ├── persistence/
│   │   ├── rerankers/
│   │   └── storage/
│   ├── indexing/
│   ├── evaluation/
│   ├── observability/
│   ├── security/
│   ├── services/
│   ├── api/
│   └── ui/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── bootstrap_dev.cmd
├── run_api.cmd
├── run_worker.cmd
├── run_ui.cmd
└── run_all_dev.cmd
```

## 依赖方向

`domain` 不依赖 FastAPI、SQLAlchemy、Streamlit 或具体模型供应商。`agent`、`ingestion`、`retrieval` 和 `indexing` 消费领域契约；`infrastructure` 实现数据库、文件、Embedding、Reranker、OCR 和索引适配；`services` 组织事务与用例；`api`/`ui` 只负责边界投影。

## 关键入口

| 入口 | 用途 |
|---|---|
| `scripts/bootstrap_dev.py` | 创建目录、执行 Alembic、初始化 Demo tenant/source |
| `scripts/run_api.py` | 启动 FastAPI |
| `scripts/run_worker.py` | 处理 ingestion/deletion 持久任务 |
| `scripts/run_ui.py` | 启动 Streamlit |
| `scripts/run_all_dev.py` | 同时监督三类本地进程 |
| `scripts/run_evaluation.py` | 按真实 Trace 阶段执行版本化评测 |

## 注释约定

源文件模块说明、函数/方法 docstring 和关键状态变量使用中英文双语；普通机械赋值不要求重复解释。注释应说明职责、约束或设计原因，禁止仅把变量名机械翻译成中文。

English summary: The package follows inward dependency boundaries. Domain contracts remain
framework-independent; adapters and delivery layers can be replaced without embedding
document-specific rules in the core.
