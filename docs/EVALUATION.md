# V4 准确率与可信性评测

最终答案不能单独证明 RAG 正确。V4 分别评估解析/切块、路由/检索、上下文/引用、答案/拒答，以及生命周期和安全竞态。

## 固定中文黄金集

正式数据集至少包含：法规条款、企业设备说明书、技术报告、Markdown/API 文档、文本 PDF、OCR 扫描或混合 PDF、中英文混排、表格/步骤，以及知识库中不存在答案的问题。

每个样例应冻结：

- 稳定样例 ID、问题和数据集版本；
- 正确 Source、Document、条款/章节和相关 Child ID；
- 参考答案；
- 是否应拒答及拒答类型；
- 文档内容哈希、解析/切块/Embedding/模型/提示词指纹。

## 指标

| 层 | 指标 | 目标 |
|---|---|---|
| 切块 | 硬边界违反、标题路径保留、父子完整、重复率、确定性 | 结构正确且可复现 |
| 路由 | Source Precision/Recall | 只选授权且相关资料源 |
| 检索 | Hit@K、Recall@K、MRR、nDCG | 正确 Child 进入候选并靠前 |
| 上下文 | Parent Coverage、Token 使用、重复证据丢弃 | 完整但不被单文档垄断 |
| 引用 | Precision、Recall、Completeness | 引用真实、精确且覆盖声明 |
| 答案 | Exact Match、Token F1、忠实度 | 只由证据支持 |
| 拒答 | 正确、错误、遗漏拒答 | 无证据时拒绝编造 |
| 可信性 | 删除竞态、CAS 冲突、硬超时、跨租户 | 状态和权限不污染 |

`enterprise_rag.evaluation.chunking_metrics` 提供确定性切块指标和两次构建一致率；`EvaluationRunner` 输出 JSON 与 Markdown 报告；`comparison.compare_reports` 对同一数据集版本执行候选门禁。

## 运行评测

先准备已经接入并标注稳定 ID 的数据集 JSON：

```json
{
  "name": "enterprise-zh-golden",
  "version": "2026-08-26",
  "examples": [
    {
      "id": "manual-power-001",
      "query": "维护前必须先做什么？",
      "expected_source_ids": ["src_..."],
      "relevant_chunk_ids": ["chk_..."],
      "reference_answer": "维护前必须断开电源。",
      "should_refuse": false
    }
  ]
}
```

运行基线和候选配置时必须使用相同数据集、租户和 Source 范围：

```bash
ENTERPRISE_RAG_ENV=evaluation uv run python scripts/run_evaluation.py \
  --dataset data/evaluation/enterprise-zh-golden.json \
  --output-dir reports/candidate \
  --tenant-id evaluation-tenant \
  --source-ids src_a,src_b
```

比较报告：

```bash
uv run python scripts/compare_evaluations.py \
  --baseline reports/baseline/evaluation_report.json \
  --candidate reports/candidate/evaluation_report.json
```

需要强制提升的指标可以重复传入：

```bash
--metric recall_at_5:0.02 --metric mrr:0.01 --metric citation_precision:0
```

## 发布门禁

1. 数据集名称/版本必须完全相同。
2. 硬边界违反数为零，超长 Child 为零，Parent-Child 完整率为 `1.0`。
3. 相同输入与快照的确定性一致率为 `1.0`。
4. 核心检索、引用和拒答指标不得低于已批准基线。
5. 目标 Recall@K/MRR 提升量由发布配置明确指定，不能靠主观观察。
6. OCR 缺页、低质量页和严重 Chunk 质量错误不能进入活动索引。
7. Parent 扩展不能降低引用正确率或提高无答案幻觉率。

## 外部运行时验收

单元测试中的伪模型只能验证状态机和算法。正式发布还必须执行真实 FAISS、目标 Embedding、目标 Reranker、Tesseract 中文 OCR、Ollama/Qwen（或生产模型）和 Docker Compose 的端到端闭环，并保存版本、硬件、耗时和报告。
