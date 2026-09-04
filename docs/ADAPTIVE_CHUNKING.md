# 结构化接入与自适应切块 / Structured ingestion and adaptive chunking

## 原则

V5 不用一个万能 Prompt 猜测所有文件，也不针对民法典、某厂商或某设备写专用逻辑。接入由三层组成：

1. Loader 只恢复格式事实：文本块、页码、标题层级和 OCR 元数据。
2. NormalizedDocument 统一正文和三层坐标。
3. StructureAdapter 按 canonical Profile 标注通用结构，再交给现有确定性切块主干。

## Profile 兼容映射

| V4 Profile | V5 canonical Profile | 说明 |
|---|---|---|
| `regulation` | `numbered_rule_document` | 条、款、项、编号制度与合同规则 |
| `manual` | `sectioned_technical_manual` | 默认手册映射；若 Source 明确以流程为主可选择 procedure |
| `technical_doc` | `sectioned_technical_manual` | API、配置、参数与技术章节 |
| `general_prose` | `general_expository` | 保守回退 |
| `academic` | `general_expository` | V5 不承诺专用学术推理，保留通用读取 |
| `narrative` | `general_expository` | V5 不承诺叙事专用语义，保留通用读取 |

一个 Source 有一个主 Profile，可在文档内部出现 warning、parameter、exception、step 等受控次级结构；只有根本不同的业务契约才应拆分 Source。

## 通用结构类型

- `heading`
- `numbered_clause`
- `procedure_step`
- `prerequisite`
- `warning`
- `parameter_table`
- `troubleshooting_entry`
- `exception`
- `general_paragraph`

它们只表达结构角色，不携带“某法典第几条”或“某型号专用步骤”的知识。

## 三层 Locator

`OriginalLocator` 保存原文件页码/块/OCR box；`NormalizedRange` 保存规范文本字符范围和 hash；`DisplayLocator` 保存用户看到的标题路径、页码和锚点。多个规范块进入同一 Chunk 时，Locator 进行有序合并。

精度规则：

- 非 PDF、未删块、清洗前后字符数相同：`exact`；
- PDF 重排、OCR、NFKC/空白清洗改变字符或删除块：`approximate`；
- 无法可靠定位：不得制造偏移，应明确降级。

## 边界算法

硬边界优先于所有分数：独立条款、步骤、warning、故障项和标题边界不能被普通语义相似度合并。软边界综合结构、语义差、长度压力、标记变化和角色变化。

Embedding 边界特征按整篇文档准备：

```text
prefetch success → all boundaries use embeddings
prefetch failure → clear cache → all boundaries use lexical cosine
document complete → release document cache
```

同一文档不允许一部分边界用向量、一部分用词法，以保证 reprocess 可复现。

## Parent–Child 与局部窗口

索引只包含精确可引用 Child；Parent 只在命中后扩展。Parent 超过单块或总 Token 预算时，使用 `previous sibling + hit + next sibling` 临时窗口。相邻块必须同时满足 tenant/source/document/version/parent/hard-boundary 一致，法规默认不跨条、SOP 默认不跨步骤、故障手册默认不跨故障项。

## 质量门

当前确定性质量门检查空块、超长块、倒置页码、重复 ID、断裂 Parent–Child、高碎片率、重复正文和弱 Profile 信号。执行成功与内容质量必须分开：Job 可以成功执行，但 QualityReport 仍可能是 warnings/review。

English summary: V5 normalizes coordinates and structure before chunking, uses generic profiles,
degrades embeddings at whole-document scope, indexes children only, and never expands context
across a hard structural boundary.
