# V4 HTTP API

默认前缀为 `/api/v1`，交互式 OpenAPI 位于 `/docs`。除健康检查外，所有端点都需要经过配置模式验证的身份。

## 认证

| 模式 | 请求 | 使用场景 |
|---|---|---|
| `demo` | 开发身份头 | 仅本机开发，生产启动会拒绝 |
| `jwt` | `Authorization: Bearer <token>` | 默认生产模式 |
| `trusted_proxy` | 代理共享密钥和清洗后的身份头 | 企业统一网关后端 |

JWT 使用 HS256，必须包含有效的 `sub`、`tenant_id`、`iss`、`aud` 和 `exp`；可包含 `roles`、`source_ids`、`group_ids`。客户端提交的租户或管理员头在 JWT 模式下不会被信任。

开发模式示例头：

```text
X-User-Id: demo-admin
X-Tenant-Id: demo-tenant
X-Roles: admin
```

下方示例统一使用 `$AUTH`：

```bash
export AUTH='Authorization: Bearer eyJ...'
```

## 健康检查

### `GET /health/live`

仅验证进程存活，返回 `status` 与 `version`。

### `GET /health/ready`

检查依赖容器、数据库与活动运行条件；用于容器健康检查。

## 资料源

### `GET /sources`

返回调用者可访问的活动资料源，已应用租户、可见性、用户组和显式授权过滤。

### `PATCH /sources/{source_id}/content-profile`

仅管理员。更新内容画像只影响后续新版本；已有文档必须显式 reprocess。

```bash
curl -X PATCH http://127.0.0.1:8000/api/v1/sources/source-id/content-profile \
  -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"content_profile":"manual","chunk_strategy_override":null}'
```

可用画像：`general_prose`、`manual`、`technical_doc`、`regulation`、`academic`、`narrative`。

## 文档

### `POST /documents`

上传 PDF、Markdown 或 TXT，并创建持久化异步任务。请求是 `multipart/form-data`，字段为 `source_id`、`file` 和可选 `title`。

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents \
  -H "$AUTH" \
  -F source_id=source-id \
  -F title='设备维护手册' \
  -F file=@manual.pdf
```

成功返回 `202`：

```json
{
  "document_id": "doc_...",
  "document_version_id": "ver_...",
  "job_id": "job_...",
  "status": "pending"
}
```

### `GET /documents/{document_id}`

返回生命周期状态、活动版本、稳定错误码、内容画像、切块策略版本和质量指标。

### `POST /documents/{document_id}/retry`

只为失败接入任务创建新 attempt，不改变不可变原文件。

### `POST /documents/{document_id}/reprocess`

使用资料源当前画像和运行配置创建新的不可变文档版本。旧活动版本继续服务，直至候选版本成功发布。

### `DELETE /documents/{document_id}`

立即进入删除 fencing，取消或阻断旧任务，重建不含该文档的活动快照，最终返回索引发布结果。响应不表示可以恢复原文件；生产操作前应按组织策略备份。

## 问答

### `POST /chat`

```bash
curl -X POST http://127.0.0.1:8000/api/v1/chat \
  -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"query":"设备维护前需要执行什么？","requested_source_ids":["source-id"]}'
```

回答响应包含 `trace_id`、`answer`、精确 Child 引用、活动 `index_version_id` 和检索轮数。引用包含文档、版本、Source、页码和原文摘录。

证据不足、文档处理中、需要 OCR、权限不足或超时时返回 `status=refused`、稳定 `refusal_reason` 和安全消息。系统故障通过统一错误响应和 HTTP 状态暴露，不会伪装成知识库拒答。

## 索引

### `GET /indexes`

仅租户管理员可查看不可变索引历史、状态、Chunk 数、配置指纹和激活时间。

### `POST /indexes/rebuild`

仅管理员。基于当前 `READY` 文档构建候选快照，验证后执行 CAS 激活；失败不影响旧活动索引。

## Trace

### `GET /traces/{trace_id}`

仅请求发起者或同租户管理员可读。返回经过脱敏的步骤和聚合指标，包括路由、检索轮次、证据数量、动态 Top-K、Parent 扩展、超时和引用验证结果，不返回密钥或未经授权正文。

## 常见状态码

| 状态码 | 含义 |
|---:|---|
| 200 | 成功或结构化问答结果 |
| 202 | 接入/重处理任务已入队 |
| 400/422 | 请求或配置字段无效 |
| 401 | 身份缺失或验证失败 |
| 403 | 租户/Source/管理员权限不足 |
| 404 | 资源不存在或对调用者不可见 |
| 409 | 生命周期、租约或索引 CAS 冲突 |
| 413 | 请求体或文件超过限制 |
| 500/503 | 系统依赖或就绪状态异常 |
