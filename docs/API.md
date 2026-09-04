# API 契约 / API contract

默认前缀：`/api/v1`。开发环境使用显式 Demo auth；生产只能使用经过配置的 JWT 或可信反向代理身份。客户端提交的 tenant/source 头本身不是可信身份。

## Chat

`POST /chat`

```json
{
  "query": "设备出现 E102 后如何处理？",
  "requested_source_ids": ["source-id"]
}
```

成功回答包含 `trace_id`、`answer`、`citations`、固定 `index_version_id` 和检索轮数；结构化拒答包含 `refusal_reason` 和安全消息。内部 RetrievalTrace 不直接通过普通用户响应暴露。

`status` 的终态为：

- `answered`：全部 required Need 得到支持；
- `partial`：至少一个 required Need 完整支持，未解决项通过 `missing_information` 披露；
- `refused`：没有可安全回答的完整 Need、存在不可裁决冲突，或 Claim/Citation 复核失败。

API v1 保留旧 `answer/citations` 字段，并新增 `items/claims/missing_information`。每条 Claim 都带 `need_ids`、`evidence_ids`、`citation_ids` 和 `verification_status`；这是 additive 兼容升级。

## Documents and jobs

| Method | Path | Result |
|---|---|---|
| POST | `/documents` | `202`，返回 document/version/job ID |
| GET | `/documents/{document_id}` | 文档、活动版本、Profile、质量指标 |
| POST | `/documents/{document_id}/retry` | `202`，支持 `Idempotency-Key` |
| POST | `/documents/{document_id}/reprocess` | `202`，原子分配版本，支持 `Idempotency-Key` |
| DELETE | `/documents/{document_id}` | `202`，立即撤销并返回 deletion job |
| GET | `/documents/jobs/{job_id}` | 通用 Job 状态、attempt 和安全错误码 |

删除响应：

```json
{
  "deletion_job_id": "job_...",
  "document_id": "doc_...",
  "status": "pending_delete"
}
```

删除请求事务立即递增 lifecycle generation、将文档标成 `PENDING_DELETE`、取消旧任务并记录 revocation；Worker 后续发布不含目标文档的新索引、清理原文件并提交 `DELETED/SUCCEEDED`。

## Sources

| Method | Path | Purpose |
|---|---|---|
| GET | `/sources` | 返回当前用户可见 Source |
| PATCH | `/sources/{source_id}/content-profile` | 管理员更新兼容 Profile/策略覆盖 |

V0.5.0 的公共 Source API 仍暴露 V4 六种 Profile 以保持客户端兼容；V5 canonical contract 已用于规范化层，但完整 `SourceContract` 管理 Schema 是当前已知边界。

## Indexes and traces

| Method | Path | Purpose |
|---|---|---|
| GET | `/indexes` | 管理员查看不可变索引历史 |
| POST | `/indexes/rebuild` | 管理员显式重建并发布新快照 |
| GET | `/traces/{trace_id}` | 按用户/管理员权限查看脱敏 Trace 摘要 |

UI 对 rebuild 要求确认；服务端发布仍使用 expected-active CAS，陈旧计划不能覆盖较新索引。

## 错误信封

```json
{
  "error": {
    "code": "STABLE_ERROR_CODE",
    "category": "conflict",
    "message": "Safe message",
    "context": {}
  }
}
```

领域类别映射为稳定 HTTP 状态：validation/parsing `422`、not_found `404`、permission `403`、conflict `409`、timeout `504`、provider/storage/index/retrieval `503`、internal `500`。

## 兼容策略

- API v1 保留旧 `AnswerResult/Citation` 字段，并 additive 增加结构化回答字段。
- 新字段优先采用 additive 方式；旧 Profile、旧状态和旧 Manifest 可读。
- `VerifiedAnswer` 已进入 V0.5.0 主链路；复杂表格 Claim 拆分和 ConflictDisclosure UI 仍属于已知边界。

English summary: API v1 remains backward compatible while exposing additive verified-answer fields;
deletion and jobs are asynchronous, and raw internal retrieval traces remain protected.
