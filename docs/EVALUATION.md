# 评测与 Trace / Evaluation and trace

## 数据层级

每项指标只读取产生它的真实阶段：

| 指标 | 正确来源 |
|---|---|
| Router precision/recall | `RetrievalTrace.routed_source_ids` |
| Dense recall | Dense 原始排名 |
| BM25 recall | BM25 原始排名 |
| RRF recall/MRR/nDCG | Fusion 排名 |
| Rerank recall/MRR/nDCG | Reranker 排名 |
| Evidence completeness | QuestionPlan Need → Evidence grade |
| Citation precision/coverage | 最终已验证 citations |
| Refusal accuracy/false refusal | Agent 终态与人工标签 |
| Unsafe answer rate | 本应拒答却回答的人工标签样本 |

最终 citations 不能用来冒充 Router 或检索排名。拒答也不能擦除已经执行的检索 Trace。

## Trace 内容与隐私

V0.5.0 保存：Router、Dense、BM25、RRF、Rerank、selected Child、Parent/local-window 映射、QuestionPlan 摘要、Evidence grade、RewriteDecision、引用结果、降级和聚合预算。候选只保存 ID/排名/分数，不复制 Chunk 正文。

Trace recorder 删除可能含 key/token/authorization/password/prompt/chunk text 的属性，字符串和集合有长度上限。配置提供 summary/diagnostic retention 和 ranked candidate limit；自动 retention 清理与角色分级诊断是正式版剩余项。

## 黄金集规则

Golden Set 不绑定易变化的随机索引 ID。每个样例应保存：

- stable document/source family；
- 文档版本或内容 hash；
- 结构锚点和原文 Locator；
- relevant evidence 等级；
- required/optional Need；
- reference answer 或明确 refusal label；
- 标注人、复核人、数据集版本和变更原因。

建议至少覆盖四类文档：法规/制度、技术说明书、设备说明书、SOP/故障排查。民法典回归包括第十三条、第十六条例外、第八条、第四至第九条聚合、精确条号和无答案问题；它只是通用算法的一个验证集，不是代码设计蓝本。

## 执行

```bash
.venv/bin/python scripts/run_evaluation.py \
  --tenant-id demo-tenant \
  --dataset tests/fixtures/evaluation_dataset.json \
  --output-dir reports/v5
```

报告记录 dataset/version、随机种子、配置/切块/Embedding/LLM/Prompt/code fingerprint、逐样例结果和聚合指标。

V4/V5 A/B 必须满足：同一数据集版本、同一授权语义、同一 reference labels、相同 K 定义和可解释的模型差异。应对置信区间和统计显著性进行人工评审，不能只比较单一均值。

## 当前验证边界

当前自动化覆盖评测层级、拒答 Trace 保留、Need Top-K、冲突边界和主要故障注入。真实民法典/手册黄金集、人工 unsafe answer 标注、模型成本与延迟基准尚未在本工作区完整运行，因此 `v0.5.0` 不对这些未执行项目发布虚构质量数字。

English summary: Evaluation consumes actual stage traces and separates retrieval, answer,
system, and governance metrics. Final citations are used only for citation metrics.
