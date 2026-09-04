# V5.1 源工程整改记录 / Source remediation record

本工程的外层目录版本为 `V5.1`，内部产品和 Python 包版本保持 `0.5.0`。V5.1 表示一次
源工程缺陷整改批次，不代表产品 API 升级。

English: `V5.1` names the outer source-remediation folder. The product and Python package remain
at version `0.5.0`; this is not an API-version change.

## 算法整改与文件映射 / Algorithm-to-file mapping

| 整改项 | 核心文件 | 已实现算法 |
|---|---|---|
| 法规条款边界 | `ingestion/regulation_chunker.py`, `semantic_chunker.py`, `structure_parser.py` | 条款锚点状态机；合并、重叠、Parent 和局部窗口的同边界约束 |
| 接入质量门 | `ingestion/quality_validator.py`, `pipeline.py` | 多条混块、缺失条款键、重复前缀检测与标准 Locator 附着 |
| 双通道索引文本 | `indexing/index_text_builder.py`, `models.py` | Dense 紧凑标题+正文首尾；BM25 完整词法正文；内容指纹 |
| 向量坍缩阻断 | `indexing/vector_quality.py`, `index_coordinator.py` | float32 字节哈希分组；区分真实重复正文与不同正文的有害重复向量 |
| 查询净化与锚点 | `retrieval/query_features.py`, `question_planner.py`, `bm25_index.py` | 来源/格式指令剥离；起止问题拆成 required Need；条款锚点高权重 |
| Need 候选配额 | `retrieval/dynamic_top_k.py` | 每个 required Need 预留候选；时间角色作为候选资格而非弱加分 |
| 命题与证据评分 | `agent/proposition_extractor.py`, `evidence_grader.py` | 可追溯句子命题；实体、时间、规范模态信号；Need 语义槽位覆盖 |
| Claim–Citation 验证 | `agent/claim_verifier.py`, `citation_verifier.py` | 词面、精确锚点、实体、时间、模态、数字联合校验；任一失败即拒答 |
| Trace 一致性 | `domain/models.py`, `repositories.py`, `chat_service.py`, `trace_service.py` | 正式持久化并授权返回 index/snapshot 身份 |
| 管理员安全 | `knowledge_service.py`, `streamlit_app.py`, `dependencies.py` | 手动空索引阻断；删除流程显式允许空快照；无变化画像不误报重处理 |

## 验证结果 / Verification results

- Ruff：通过。
- MyPy：156 个源文件通过。
- Pytest：110 passed，2 skipped。
- 跳过原因：当前容器未安装真实 FAISS runtime 与 PyMuPDF `fitz`；Windows、Ollama 和真实
  《民法典》数据仍应在目标电脑执行验收。

English: Static checks and all available automated tests pass. Real FAISS/OCR and the final
Windows/Ollama/Civil-Code acceptance run remain target-machine checks and are not claimed here.
