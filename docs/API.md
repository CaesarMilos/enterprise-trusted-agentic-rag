# API

所有接口位于 `/api/v1`。开发配置允许使用以下 Demo Header：

```text
X-User-ID
X-Tenant-ID
X-Roles
X-Source-IDs
X-Group-IDs
```

生产配置禁用 Demo 身份；若启用将无法通过 Settings 校验。

| 方法 | 路径 | 功能 |
|---|---|---|
| `POST` | `/documents` | 上传资料，返回 `202`、Document/Version/Job ID |
| `GET` | `/documents/{id}` | 查询权限范围内的文档状态 |
| `DELETE` | `/documents/{id}` | 两阶段删除并重建索引 |
| `POST` | `/documents/{id}/retry` | 重试失败接入任务 |
| `POST` | `/documents/{id}/reprocess` | 使用 Source 当前画像创建新处理版本 |
| `GET` | `/sources` | 列出调用者可见资料源 |
| `PATCH` | `/sources/{id}/content-profile` | 管理员更新资料源内容画像 |
| `GET` | `/indexes` | 管理员查看不可变索引历史 |
| `POST` | `/indexes/rebuild` | 管理员重建活动索引 |
| `POST` | `/chat` | 返回已验证答案或结构化拒答 |
| `GET` | `/traces/{id}` | 查询本人或管理员可见的脱敏 Trace |
| `GET` | `/health/live` | 进程存活 |
| `GET` | `/health/ready` | 数据库就绪 |

错误使用稳定信封：

```json
{
  "error": {
    "code": "ACTIVE_INDEX_NOT_FOUND",
    "category": "retrieval",
    "message": "No active knowledge index is available for this tenant.",
    "context": null
  }
}
```

API Router 只能调用 Service。索引、Repository、FileStore 和模型 Provider 不会直接暴露给 HTTP 层。

上传请求体超过配置上限时，ASGI middleware 在 multipart 解析前返回：

```json
{
  "error": {
    "code": "REQUEST_BODY_TOO_LARGE",
    "category": "validation",
    "message": "The request body exceeds the configured size limit."
  }
}
```
