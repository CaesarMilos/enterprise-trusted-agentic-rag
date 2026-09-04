# Enterprise Trusted Agentic RAG v0.5.0（V5.1 源工程整改版）

外层目录使用 `enterprise-trusted-agentic-rag-V5.1`，用于与旧 Windows 11 工程并存；
Python 包、API 和产品版本仍保持 `0.5.0`，本次不改变 V5 的版本定位。

English: The outer source folder is named `enterprise-trusted-agentic-rag-V5.1` so it can coexist
with the prior Windows project. The package, API, and product version remain `0.5.0`.

面向企业内部说明类、规则类和指示类文档的单节点高可信 RAG 参考实现。它不是“民法典专用系统”：法规、企业制度、技术说明书、设备手册、SOP、故障排查资料和一般说明文本通过统一内容契约、四种通用结构 Profile 与可替换适配器进入同一条主链路。

English: A single-node reference implementation for trusted enterprise RAG over regulations,
policies, technical manuals, device instructions, procedures, troubleshooting guides, and general
expository documents.

## V5 四层能力 / Four capability layers

| 层级 | 核心职责 | 当前 V0.5.0 状态 |
|---|---|---|
| 1. 知识治理与可信接入 | Source 契约、Profile 兼容、NormalizedDocument、三层 Locator、质量与 Provenance | 通用结构、Locator 和独立质量报告已接入；完整 SourceContract 管理 API 仍待完成 |
| 2. 结构化检索与证据 | QuestionPlan、required Need、精确锚点、混合检索、Need-aware Top-K、Parent/局部窗口 | 已进入在线主链路 |
| 3. 受验证回答 | Need 级覆盖、命题关系、引用当前有效性、部分回答与 Claim–Evidence 协议 | 确定性命题抽取与实体/时间/模态/数字/锚点验证已进入主链路；LLM 模糊复核仍待完成 |
| 4. 生产正确性与治理 | Lease/Generation、Deadline、原子发布、固定快照、异步删除、Trace、评测、迁移与启动 | 核心闭环已实现；真实 FAISS/OCR/Windows 验收仍需目标环境执行 |

## 已实现的重要修复 / Implemented corrections

- 取消、失租、租约过期和文档 generation 失效使用不同结果；旧 Worker 不能覆盖新租约。
- Embedding 文档级预取失败时整篇确定性降级为 lexical，相同文档不会混用两种边界模式。
- Provider 调用共享有界执行器并接收剩余 Deadline，超时结果不会拖住 API 或无限占满线程池。
- reprocess 使用数据库原子计数器和幂等键，不再执行 `max(version) + 1`。
- PDF、Markdown、TXT 先转换为 `NormalizedDocument`，保留 original/normalized/display 三层定位。
- 问题格式指令不参与知识覆盖；精确条款、章节、步骤和错误码在改写中必须保留。
- Dynamic Top-K 可按 required Need 和明确结果项数扩张，并为 Need 预留候选。
- 法规按“条”建立不可跨越的硬边界，重叠、合并和 Parent/local-window 都不得越条。
- Dense 与 BM25 分离索引文本：Dense 使用紧凑标题上下文和正文首尾，BM25 保留完整词法正文。
- 发布前检测不同正文产生的完全相同向量；超过阈值时拒绝激活候选索引。
- 查询末尾的资料源/格式指令不会污染知识查询，精确条款锚点获得确定性高权重。
- “何时开始/何时终止”等独立 Need 必须命中对应时间角色，不能由相似条文占用配额。
- 完整、部分和拒答使用不同状态；部分回答只覆盖完全支持的 Need，并披露缺失项。
- 每条公开 Claim 必须确定性绑定 Need、Evidence 和已验证 Citation，否则整次回答拒绝返回。
- 最终 Claim 还需通过实体、时间、规范模态、数字和精确锚点一致性验证。
- 接入质量结论、指标、警告和降级码写入独立 `QualityReport`，不与 Job 状态混用。
- 删除立即进入 `PENDING_DELETE`、递增 generation、记录 revocation，然后由持久 Worker 异步重建与清理。
- 问答固定索引、Source 和文档版本集合；普通 reprocess 可完成旧快照，删除或 Source 撤销立即阻断返回。
- Trace 将 `snapshot_id` 和 `index_version_id` 持久化并通过授权接口返回，不再只依赖自由属性。
- 管理员手动重建禁止激活空索引；删除最后文档仍可显式发布空快照以完成撤权。
- 评测读取 Router/Dense/BM25/RRF/Rerank 的真实排名，拒答不会擦除检索 Trace。
- Alembic 取代启动时手写 `ALTER TABLE`；生产只检查 revision，开发环境可一键初始化。

## 快速启动 / Quick start

Python 支持 3.11–3.12。推荐先复制 `.env.example` 为 `.env`，并确保本地 Ollama 或兼容模型服务可用。

```bash
python -m venv .venv
# Linux/macOS
.venv/bin/python -m pip install -e ".[dev,local-models,ocr]"
.venv/bin/python scripts/bootstrap_dev.py
.venv/bin/python scripts/run_all_dev.py
```

Windows CMD：

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev,local-models,ocr]"
bootstrap_dev.cmd
run_all_dev.cmd
```

默认本地地址：API `http://127.0.0.1:8000`，UI `http://127.0.0.1:8501`。项目已按 src-layout 安装，不需要手工设置 `PYTHONPATH`。

## 质量检查 / Quality gates

```bash
.venv/bin/ruff check src tests migrations scripts
.venv/bin/mypy src/enterprise_rag
.venv/bin/pytest -q
```

本仓库当前自动化结果与未执行项记录在 [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md)。不能把因缺少 FAISS、PyMuPDF、Tesseract、Ollama 或 Windows 环境而跳过的检查写成“已通过”。

## 文档索引 / Documentation

- [工程设计与四层契约](docs/ENGINEERING_DESIGN.md)
- [结构化接入与切块](docs/ADAPTIVE_CHUNKING.md)
- [API 契约](docs/API.md)
- [部署、升级与恢复](docs/DEPLOYMENT.md)
- [评测与 Trace](docs/EVALUATION.md)
- [安全边界](docs/SECURITY.md)
- [工程结构](docs/PROJECT_STRUCTURE.md)
- [实现与验证状态](docs/IMPLEMENTATION_STATUS.md)

## 诚实边界 / Honest scope

`v0.5.0` 是面向生产可信验收的单节点参考实现，不宣称已经具备分布式高可用、跨区域灾备或无限规模能力。受约束命题抽取、LLM 冲突模糊复核、SourceContract 管理闭环、黄金集人工治理以及真实 Windows/OCR/FAISS/Ollama E2E 是当前版本明确保留的验收边界。
