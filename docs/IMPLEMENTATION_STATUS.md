# V5 实现与验证状态 / Implementation status

版本：`0.5.0`。本页是事实清单，不是路线图；“已实现”表示代码进入主链路，“已验证”表示存在当前环境实际执行的自动化或 E2E 证据。

## 已实现并由自动化覆盖

- Alembic V4 baseline 与 V5 expand migration；可识别合法旧 V4 schema，拒绝未知未版本化 schema。
- SQLite 数据库父目录与 uploads/indexes/traces 运行目录自动创建。
- Lease 结果分流：cancel、ownership lost、expired、generation stale。
- Worker CAS 终态、心跳取消、旧租约写保护和删除 generation fence。
- Embedding 整篇预取、lexical 整篇降级、文档级缓存释放。
- 共享有界 Provider 执行器、剩余 Deadline 传递和超时返回上限。
- 原子文档版本分配与 retry/reprocess 幂等键。
- 四种 canonical Profile、NormalizedDocument、三层 Locator、通用结构适配器。
- QuestionPlan、格式指令剥离、精确锚点、required Need、改写漂移门禁。
- Need-aware Dynamic Top-K、文档/Parent 去重、同硬边界局部窗口。
- 法规条款硬边界、正文优先双通道索引文本、精确重复向量发布门禁。
- Need 级证据评分与时间角色资格过滤；“应当/不得”不再触发全局冲突。
- 命题关系确定性判定：同主体/动作/对象/条件/时间/authority 且模态互斥才判冲突。
- 确定性命题抽取及 Claim 的实体、时间、模态、数字、锚点一致性验证。
- 完整/部分/拒答分流；部分回答只生成已完整支持的 required Need，并披露未解决项。
- `VerifiedAnswer`、`AnswerItem`、`AnswerClaim`、`MissingInformation` 通过 additive API 字段进入主链路。
- Claim 无法绑定 Need/Evidence/Citation 时整体拒答，不退化为无审计自然语言。
- Worker 在 fencing 事务中写入独立 `QualityReport`、质量指标、警告与降级码。
- 请求固定 index/source/document-version 快照；普通切换可完成，删除/撤权立即覆盖。
- 异步删除 `202`、持久 deletion job、状态查询、索引重建、文件清理和终态提交。
- Citation 返回前重新检查 Source、Document、DocumentVersion 与固定 scope。
- Router、Dense、BM25、RRF、Rerank、selected Child 和 Parent 映射 Trace。
- `snapshot_id` 与 `index_version_id` 作为 Trace 正式字段持久化并返回。
- 评测使用正确层级排名，并计算 false refusal/unsafe answer rate。
- V5 Manifest 保存 tokenizer、normalizer、chunk strategy、内容 hash 与映射指纹。
- 统一开发启动脚本、Windows CMD 入口、UI Job/Document/Trace 状态和重建确认。

## 已接入骨架但仍待完成的治理闭环

| 能力 | 已有部分 | 正式版尚需完成 |
|---|---|---|
| SourceContract | 领域契约、Profile 映射、ORM 字段 | 管理 API、版本冻结展示、完整迁移 UI |
| QualityReport | 领域模型、独立表、Worker 幂等写入和 Repository 查询 | 管理 API 展示、UI 独立报告详情和人工复核动作 |
| VerifiedAnswer | 逐句 Claim 绑定、完整校验、Partial 状态和 API v1 additive 投影 | 冲突披露 UI、版本化 API 文档及复杂表格 Claim 拆分 |
| Proposition | 领域模型、确定性抽取器、语义槽位校验与关系 Judge | LLM 模糊复核、authority/version 优先级策略 |
| OperationalEvent | ORM 表 | 所有状态转换统一写审计事件与防篡改导出 |
| Trace 治理 | 脱敏、候选上限配置、数据库摘要 | 自动 retention 清理与角色分级诊断视图 |

## 本次工作区验证

当前环境执行：

```text
Ruff: passed
MyPy strict: passed
Pytest: 110 passed, 2 skipped
```

跳过项：

- FAISS 真实 E2E：环境未安装/加载真实 FAISS runtime。
- OCR 真实 E2E：环境未安装 PyMuPDF `fitz`；也不能据此声称 Tesseract 已验收。

已存在一个 FastAPI/Starlette `TestClient` 弃用警告，不影响业务测试，但应在依赖升级批次处理。

## 正式 v0.5.0 发布阻断项

1. 用真实民法典、技术说明书、设备说明书和 SOP 运行同版黄金集。
2. 验证第八条、六项聚合、第十六条例外和无答案拒答，不只运行合成单元测试。
3. 完成复杂表格回答的 Claim 拆分、冲突披露 UI 和 LLM 模糊命题复核。
4. 完成 SourceContract 管理闭环及 QualityReport 管理 API/UI。
5. 在 Windows、Ollama、FAISS、OCR、Docker 环境分别留下可复现实测报告。
6. 量化 P50/P95/P99、最大文件/页数/Chunk、并发、资源与模型成本。
7. 执行数据库备份恢复、索引重建、迁移失败回滚与删除证明演练。

English summary: V0.5.0 implements the principal correctness, retrieval, partial-answer, claim-binding,
and quality-report paths. Skipped real runtimes and remaining governance integrations prevent a
final production-complete claim.
