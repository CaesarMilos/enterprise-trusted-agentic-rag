# 安全边界与威胁模型 / Security boundaries and threat model

## 信任边界

- HTTP 身份：只信任经过配置的 JWT 或受控反向代理；Demo auth 仅允许 development。
- tenant/source/document/version：所有 repository 查询显式携带 tenant，Router 只能在预授权 Source 内选择。
- 文档正文：始终是不可信数据，不能覆盖 System Prompt、ACL、工具权限或引用规则。
- Provider：LLM/Embedding/OCR/Reranker 是外部或本地不可信依赖，必须有 timeout、fingerprint、数据出域说明和降级策略。
- 文件系统：上传和索引键为服务端生成的不透明 ID，所有目标必须位于 tenant 隔离根目录。

## 威胁—控制矩阵

| 威胁 | 当前控制 | 剩余验证 |
|---|---|---|
| 跨租户/越权检索 | tenant predicates、ACL 前置过滤、Citation 返回前复核 | 全 API 属性测试与外部渗透测试 |
| 删除后旧缓存/快照返回 | revocation epoch、PENDING_DELETE、snapshot loader 和 final verifier | 多进程并发压力测试 |
| 文档 Prompt Injection | 不可信文档边界、证据限定 Prompt、无文档工具权限 | 对抗文档黄金集 |
| 路径穿越 | opaque storage key、safe segment、root-relative 校验 | parser/压缩格式扩展前重新评审 |
| 上传炸弹/超大请求 | ASGI request-body limit、文件级 limit、类型/签名校验 | PDF 对象/页数/解压比限额 |
| Provider 永久阻塞 | 剩余 Deadline、HTTP timeout、共享有界执行器 | 需要绝对 kill 时使用进程隔离 |
| Secret 泄漏 | env/secret store、Trace key 过滤、不记录 Prompt/正文 | 集中日志 DLP 和 Secret rotation |
| Trace 成为敏感仓库 | 默认 summary、候选只存 ID、值长度上限 | 自动 retention 与分级访问 |
| 依赖漏洞 | 版本上限和可重现 lock | SBOM、签名、持续 CVE 扫描 |
| 恶意/漏洞 PDF | 文件验证、隔离 Loader 接口 | sandbox parser、CPU/内存/页数预算 |

## 权限撤销优先级

普通 reprocess/索引切换允许已开始请求完成固定快照；Source 停用、权限撤销和文档删除立即优先。CitationVerifier 在返回前重新读取当前 Source、Document 和 DocumentVersion；失败时结构化拒答，不能返回“几分钟前还合法”的正文。

## 日志和 Trace

禁止记录 API key、Authorization、密码、完整 Prompt、完整 Chunk 正文和上传文件。错误响应只包含稳定 code/category、安全 message 和受限 context；未知异常不得把堆栈或 Provider 响应返回客户端。

## 数据外发

部署者必须为每个 Provider 记录：数据是否出域、区域、保留策略、模型训练策略、传输加密、超时/重试、成本和替换测试。Provider 抽象本身不等于合规；如果企业禁止正文出域，应选择本地模型或在发送前实施获批脱敏。

## 正式版门禁

- 威胁—控制—测试矩阵逐项关联自动化或演练证据；
- 依赖 SBOM、漏洞扫描和许可证清单；
- parser sandbox/资源预算；
- 审计日志完整性与防篡改导出；
- Trace retention 与管理员/开发者分级；
- 删除证明和备份恢复不复活 revoked 内容；
- 多租户越权、Prompt Injection 和恶意 PDF 对抗测试。

English summary: V5 treats identity, document content, providers, traces, and filesystem paths as
separate trust boundaries. Current controls are meaningful but do not replace deployment-specific
penetration, compliance, SBOM, and recovery evidence.
