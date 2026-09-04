# V5 工程设计 / Engineering design

## 定位

V5 是“企业高可信知识问答的单节点参考实现”，不是面向某一本法典的定制搜索器。法规、制度、合同、技术手册、设备说明书、SOP、故障排查和一般说明文本共享稳定领域契约；具体格式差异只存在于 Loader、Profile 和 StructureAdapter 边界。

## 四层能力

### 第一层：知识治理与可信接入

输入先由 Source 决定主 Profile，DocumentVersion 冻结最终策略快照。V5 canonical Profile 为：

- `numbered_rule_document`：法规、制度、合同和编号规则；
- `sectioned_technical_manual`：技术/设备手册、参数、安全和故障排查；
- `procedure_guide`：SOP、安装、维护和操作流程；
- `general_expository`：无法可靠归入前三类的一般说明文本。

V4 六种 Profile 通过显式映射兼容读取，不修改旧数据含义。管理员显式配置的置信度是 `None`，只有自动画像才可保存真实 confidence。

每份文档进入 `NormalizedDocument`，包含：

- `OriginalLocator`：页码、原始块和可选 OCR box；
- `NormalizedRange`：清洗后字符区间和内容 hash；
- `DisplayLocator`：标题路径、页码和结构锚点。

清洗改变字符数、删除块、OCR 或 PDF 重排时，定位必须标记 `approximate`，不能伪称 exact。

### 第二层：结构化检索与证据

`QuestionPlanner` 把问题拆为：

- `knowledge_query`；
- `ResponseContract`；
- required/optional `InformationNeed`；
- exact anchors。

“请根据文档回答、分别列出、给出引用”不参与知识覆盖；条款、章节、步骤、错误码和型号不可在 rewrite 中丢失。明确结果项数可以扩大候选覆盖，但不会凭空制造未命名的语义 Need。

检索顺序为 Router → Dense/BM25 → RRF → Rerank → Need-aware Top-K → Parent/Local Window → Evidence Bundle。每个阶段保留真实排名。局部窗口只能合并同 tenant/source/document/version/parent/hard-boundary 的相邻 Child。

### 第三层：受验证回答

证据充分性按 required Need 向量判断：`SUPPORTED / PARTIALLY_SUPPORTED / UNSUPPORTED /
CONFLICTING / AMBIGUOUS`。可选 Need 不降低完整性。

冲突不是关键词共现。只有核心命题一致、条件/时间/authority 范围重叠且模态互斥才可确定为 conflict；缺字段时必须是 ambiguous，例外关系单独披露。LLM 未来只允许在规则无法判断且影响结论时复核现有 evidence span，不得补充外部知识。

公共 V1 保留兼容 `answer/citations` 字段，并 additive 输出 `AnswerItem`、`AnswerClaim` 和 `MissingInformation`。完整支持返回 `answered`；至少一个 required Need 完整支持且其余项缺失时返回 `partial`；仅有低覆盖部分证据仍拒答。每条 Claim 必须绑定 Need、Evidence 和验证后的 Citation，无法确定绑定时整体拒答。

### 第四层：生产正确性与治理

任务、文档、文档版本、索引和质量报告使用独立状态机。Lease 检查严格区分取消、所有权丢失、过期和 generation stale。所有耗时操作在短数据库事务之外，发布事务用 expected active index + job fence + document generation 做 CAS。

问答开始时固定 index/source/document-version 集合并持久化 snapshot lease：

- 正常 reprocess/索引切换：已开始请求可以完成旧快照；
- 文档删除或 Source 撤销：立即优先于旧快照，回答返回前必须失败；
- 物理文件清理：异步删除 Worker 发布不含目标文档的索引后执行。

Provider 接收剩余 Deadline，不能中断的本地调用由共享有界执行器隔离。普通线程超时只保证调用方按时返回；绝对硬杀死仍需要进程隔离。

## 发布原子性

外部索引先写 `{index}.staging`，完成 checksum、重新加载和一致性校验后原子 rename。数据库激活事务统一提交新 index ACTIVE、旧 index RETIRED、文档 active version 和 job SUCCEEDED；事务失败则删除从未激活的候选目录。

## 可追溯链

目标反查链：

```text
Answer → Claim → Evidence/Citation → Child → Locator → DocumentVersion
       → Provenance → Original file
```

V0.5.0 已实现 Answer → Claim → Evidence/Citation → Child → Locator → Version 和分阶段 RetrievalTrace；Provenance 公共查询与受约束命题抽取仍属于当前已知边界。

## 设计边界

- 不使用文档正文里的命令作为系统指令；正文始终放在不可信数据边界内。
- 不用最终 citations 计算检索指标。
- 不用管理员显式 Profile 冒充 `confidence=1.0`。
- 不跨法规条款、SOP 步骤或故障项硬边界扩展上下文。
- 不把单节点参考实现描述为分布式高可用系统。

English summary: V5 separates ingestion governance, structured retrieval, verified answering, and
production correctness into stable contracts. Format-specific logic ends at adapters; lifecycle,
evidence, authorization, and evaluation remain document-agnostic.
