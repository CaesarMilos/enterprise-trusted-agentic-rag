# V4 安全设计

## 信任边界

外部客户端只连接网关。网关删除客户端提供的用户、租户、角色、Source、用户组和代理密钥头，再转发到内部 API。API 只根据经过密码学验证的 JWT，或经过共享密钥验证的可信代理身份构造 `UserContext`。

## 认证模式

三种模式互斥：

- `demo`：仅开发配置；生产环境选择它会拒绝启动。
- `jwt`：生产默认；验证 HS256、签名、`exp`、`nbf`、`iss`、`aud`、`sub` 和 `tenant_id`。
- `trusted_proxy`：只允许位于受控代理之后；请求必须携带进程环境中的共享密钥。

JWT 密钥读取自 `ENTERPRISE_RAG_JWT_SECRET`。代理密钥读取自 `ENTERPRISE_RAG_PROXY_SECRET`。密钥不得进入 YAML、镜像、Trace、日志或错误响应。

## 授权与租户隔离

所有文档、版本、Chunk、任务、索引和 Trace 都带 `tenant_id`。Repository 查询显式包含租户条件；在线检索还必须把请求 Source 范围与用户允许范围求交集。Source Router 只在授权候选内工作，不能扩大 ACL。

管理员只在当前租户内拥有重建索引、修改画像和查看租户 Trace 的权限。`requested_source_ids` 只是进一步收窄，不是授权声明。

## 文件和解析安全

- ASGI 中间件在 multipart 解析前限制总请求体；端点再限制单文件字节数。
- 后缀、MIME 和文件签名联合校验，原文件路径由服务端稳定 ID 生成。
- 租户目录隔离、路径穿越防护、临时文件清理、原子移动和 SHA-256 校验。
- PDF/OCR/文本异常转换为稳定错误，不把原文或内部路径暴露给客户端。

## 生命周期与索引安全

删除请求递增 `lifecycle_generation`，使旧任务的快照立即失效。Worker 的租约、attempt token、取消状态和 generation 共同组成 fencing。活动索引发布使用 CAS；请求固定一个索引快照，避免问答过程中读到半发布状态。

## 模型与提示词安全

- 模型只收到调用者授权的 Evidence Pack。
- Query Rewrite 不得改变原始权限范围，最多执行配置次数。
- 回答必须引用当前快照的真实 Child；引用校验失败则拒答。
- LLM 边界复核只接收相邻局部单元，只在模糊分数带触发并受单文档调用上限约束。
- Trace 记录指纹、计数和原因，不记录 API Key。

## 容器基线

运行用户固定为 UID/GID `10001`；文件系统只读，仅数据卷、模型缓存和 `/tmp` 可写；容器删除 Linux capabilities 并启用 `no-new-privileges`。API 在生产 Compose 中不映射主机端口，只有 Nginx 网关公开。

## 发布前安全测试

- 伪造 `X-Roles: admin` 和 `X-Tenant-Id` 无效。
- JWT 错误签名、错误 issuer/audience、过期和未生效令牌被拒绝。
- 跨租户 Source、文档、索引和 Trace 不可见。
- 删除与 Worker 并发时旧任务无法写回或发布。
- 上传超限、路径穿越、错误签名文件被拒绝。
- 生产环境缺少认证密钥时进程在监听端口前失败。

本工程提供应用级安全边界，但生产部署仍需 TLS、密钥轮换、镜像扫描、依赖漏洞扫描、数据库备份、日志留存和基础设施访问控制。
