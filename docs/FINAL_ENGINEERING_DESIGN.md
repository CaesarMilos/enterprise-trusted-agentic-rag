# V1 最终工程设计基线

## 产品目标

本项目是面向企业内部说明书与技术文档的可信 Agentic RAG 系统。管理员接入文本型 PDF、Markdown 或 TXT，并在 Source 级声明 `general_prose`、`manual` 或 `technical_doc` 内容画像。系统据此选择确定性结构感知切块策略，形成不可变文档版本与索引快照；用户不必手选知识库，系统只在权限允许的资料源内自动路由和检索，并返回可定位、可验证的引用。扫描或混合 PDF 明确进入 `NEEDS_OCR`，证据不足、引用不可靠或请求超出边界时必须拒答。

## 冻结约束

1. 使用分层单体，不拆微服务。
2. Domain 不依赖 FastAPI、SQLAlchemy、FAISS 或模型 SDK。
3. 第一版使用显式 Python 状态机，不使用 LangGraph，不做多 Agent。
4. `Document` 表示逻辑生命周期，`DocumentVersion` 表示不可变上传版本。
5. 同一文档版本、文本、顺序和 Chunker 版本必须生成相同 `chunk_id`。
6. Dense、BM25、Source Catalog 必须消费同一个 `IndexBuildPlan`。
7. 索引只写 Staging；Manifest 和重新加载校验成功后才能发布。
8. ACTIVE 切换是数据库事务；新索引失败时旧 ACTIVE 继续服务。
9. `UserContext` 只能由认证层创建；ACL 必须在路由和检索前落实。
10. 一次问答固定一个 `index_version_id`，中途不能切换。
11. Dense 与 BM25 并行召回，通过 RRF 融合；Reranker 失败回退到 RRF。
12. Dynamic Top-K 为 3～10，并服从上下文预算与文档多样性限制。
13. Agent 最多执行首次检索加两次改写重检索。
14. 文档正文是“不可信输入”，不得成为系统指令。
15. CitationVerifier 重新检查引用存在、ACL、版本、位置和基础事实支持。
16. 无证据、系统错误、超时、不支持和不安全请求必须分别处理。
17. Streamlit 只调用 FastAPI，不得直接访问数据库、索引或模型。
18. 评估固定数据集、索引、配置、Chunker、模型、Prompt、随机种子和代码版本。

## 资料接入状态

```text
PENDING
→ PROCESSING
→ READY

任一步骤失败 → FAILED

READY
→ PENDING_DELETE（立即从活动查询中排除）
→ 重建并发布不含该文档的新索引
→ DELETED
```

Worker 通过 SQLite 持久化任务和租约工作。昂贵解析发生在短事务之外；Chunk 先持久化但文档保持 `PROCESSING`。索引构建、文件系统发布完成后，`Index ACTIVE`、`Document READY` 和 `Job SUCCEEDED` 在最终事务中一起切换。

## Agent 终态

```text
ANSWERED
REFUSED
UNSUPPORTED
ERROR
TIMEOUT
```

只有通过 CitationVerifier 的草稿才能进入 `ANSWERED`。模型输出 `INSUFFICIENT_EVIDENCE`、证据评分不足或引用验证失败均进入明确拒答，而不是伪装成系统异常。

## V1 不包含

- 旧 LSTM；
- Web Search；
- OCR；
- Google Drive、Notion 等外部连接器；
- 远程向量数据库；
- 微服务；
- 多 Agent；
- LangGraph；
- 流式回答。

这些边界用于保证个人工程能够完整运行、测试、解释和演示。
