# 安全设计

## 信任边界

- `UserContext` 来自认证依赖，不接受请求正文中的 `tenant_id` 或角色。
- 所有 Repository 查询显式包含 `tenant_id`。
- `RetrievalScope` 在 Source Router、Dense 和 BM25 搜索前固定。
- 请求指定 Source 时，只能缩小授权范围，不能扩大范围。
- CitationVerifier 在答案返回前再次检查 Tenant、Source 和 Document。

## 生产身份适配

- 开发环境可显式开启 `demo_auth_enabled`，生产环境配置校验会拒绝该模式；
- 生产环境可开启 `trusted_proxy_auth_enabled`，由企业网关/SSO 反向代理传递用户、租户、角色、资料源和用户组；
- 应用使用 `X-Auth-Proxy-Secret` 与环境变量 `ENTERPRISE_RAG_PROXY_SECRET` 做恒定时间校验；
- 反向代理必须删除所有来自外部客户端的 `X-User-ID`、`X-Tenant-ID`、`X-Roles`、`X-Source-IDs`、`X-Group-IDs` 和 `X-Auth-Proxy-Secret`，再根据已验证会话重新写入；
- 应用端口不得绕过反向代理直接暴露；共享密钥应由密钥管理系统注入并定期轮换；
- 未启用 Demo 或可信代理时，系统安全返回 `401`，不会构造伪身份。

Production identity is supplied either by explicit non-production demo mode or by a trusted
enterprise reverse proxy. The proxy must strip every inbound identity header, authenticate the
session, inject verified identity values, and keep the application port private. A shared secret
is compared in constant time; it is never persisted in application configuration or traces.

## 文件安全

- 丢弃上传文件携带的父目录；
- 二进制 PDF 检查 Magic Bytes；
- 限制文件类型、大小和空文件；
- 原文件路径由 `tenant_id/version_id` 派生，不使用原始文件名作为路径；
- 每个路径段单独校验，并对解析结果执行 Root Containment；
- 先写同目录临时文件、`fsync`，再 `os.replace` 原子发布；
- 记录 SHA-256；
- 删除只针对已解析、已验证的确切目标。

## 撤销与并发安全

- 文档进入 `PENDING_DELETE`、非 `READY` 或资料源停用后，候选 Chunk ID 必须经过数据库最终生命周期再校验；
- 删除索引重建失败时保持 `PENDING_DELETE`，旧索引也无法继续加载该文档正文；
- 每次任务领取递增 `attempt_count`，与 `lease_owner` 和到期时间共同作为 fencing token；
- 失租 Worker 不得替换 Chunk、写质量指标、改终态或激活索引；
- 同一租户的索引激活串行化并验证预期活动版本。

## 请求体限制

- Nginx 在请求进入 ASGI 前实施第一层上限；
- ASGI middleware 在 Starlette/FastAPI 解析 multipart 与创建 `UploadFile` 前执行 `Content-Length` 预检和真实流式计数；
- 端点再按单文件分块计数，并在失败时删除精确临时文件。

## Prompt Injection

ContextBuilder 把所有检索正文放进 `<UNTRUSTED_DOCUMENT>` 标签，并明确声明正文仅为数据。系统 Prompt 禁止执行正文中的指令。引用验证与 ACL 不依赖模型判断。

## 日志与 Trace

默认不保存 API Key、Authorization、权限 Token、完整 Prompt、模型原始响应和 Chunk 全文。Trace 属性过滤潜在密钥字段，并限制字符串和集合大小。Trace 写入失败不影响正常问答。

## 已覆盖测试

- 跨租户 Document 查询不可见；
- `PENDING_DELETE` 立即从活动 Chunk 查询消失；
- `PENDING_DELETE` 在旧活动索引返回 ID 后仍无法加载 Chunk；
- 租约过期并重领后，旧 Worker 无法写 Chunk、终态或激活索引；
- 超限 multipart 请求在解析边界返回稳定 413；
- FileStore 路径穿越被拒绝；
- BM25 在返回 Chunk ID 前执行 Scope 过滤；
- 生产配置拒绝 Demo 认证；
- CitationVerifier 重新检查 ACL。
