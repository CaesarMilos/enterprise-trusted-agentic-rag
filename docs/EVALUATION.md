# 评估设计

评估集必须包含明确的 `name`、`version` 和唯一 Example ID。每条样本可定义：

```json
{
  "id": "policy-001",
  "query": "年假是否需要经理审批？",
  "expected_source_ids": ["src_xxx"],
  "relevant_chunk_ids": ["chk_xxx"],
  "reference_answer": "年假需要经理审批。",
  "should_refuse": false
}
```

## 指标

| 类别 | 指标 |
|---|---|
| Routing | Source Precision、Source Recall |
| Retrieval | Hit@5、Recall@5、MRR、nDCG@5 |
| Answer | Exact Match、Token F1 |
| Citation | Citation Precision、Citation Recall、Completeness |
| Refusal | Correct Refusal、False Refusal、Missed Refusal |

## 可复现指纹

每份报告记录：

```text
dataset_version
index_version
config_fingerprint
chunker_version
embedding_fingerprint
llm_fingerprint
prompt_version
random_seed
code_version
```

`scripts/run_evaluation.py` 通过正式 ChatService 运行评估，并生成：

```text
reports/evaluation_report.json
reports/evaluation_report.md
```

切块消融实验的 `fixed`、`semantic`、`dynamic_size`、`paragraph` 必须分别产生 Chunk 和索引版本，不能共享索引。
