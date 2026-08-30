# V4 实现与验证状态

本文件只记录当前源码中可以核对的事实，不把缺少外部运行时的项目写成已完成。

## 已实现：生产可信化

- `lifecycle_generation` 删除 fencing、删除请求/完成时间和不可逆删除状态。
- 任务 generation 快照、取消请求/原因、租约、attempt token、心跳和失效 Worker 写入阻断。
- 文档、任务、索引显式状态机；Worker 异常不会覆盖删除状态。
- 统一候选索引构建、Manifest 校验、重新加载验证、租户级 CAS 激活、失败状态收口和旧活动版本保留。
- Agent 单调时钟硬截止；检索、改写、回答和引用校验前后检查，模型子调用接收剩余预算。
- `demo`、`jwt`、`trusted_proxy` 互斥认证；生产 Demo 禁用和密钥缺失 fail-closed。
- JWT HS256 的签名、时效、issuer、audience、用户和租户声明验证。
- JWT 模式忽略客户端伪造身份头；可信代理模式要求共享密钥；Nginx 清洗身份头。
- 开发/生产 Compose 分离、API 内网暴露、非 root 容器、只读根文件系统和依赖锁。
- SQLite 启动时幂等补充 V4 生命周期、任务取消、版本策略和索引状态列。

## 已实现：自适应中文 RAG

- PDF/Markdown/TXT 统一 Loader、PDF 逐页质量检测与可插拔 Tesseract OCR。
- 六种内容画像和低置信度通用回退。
- 标题、章/节/条/款/项、步骤、警告、参数、API、代码、表格和自然段结构识别。
- 保护 URL、小数、版本号、括号和引号的中文句子安全切分。
- 五特征自适应边界公式、动态长度阈值、批量 Embedding、缓冲区质心连续性和完整边界 Trace。
- 硬边界优先；LLM 仅复核模糊分数带，且有单文档预算与确定性失败回退。
- 过长单元安全切分、同父结构短块合并、只写入检索文本的完整句重叠。
- 稳定 Child/Parent ID、双向关系、Child-only 建索引、Parent 预算扩展和 Child 精确引用。
- 中文字符/二元词组/英文词/条款锚点 BM25、向量召回、RRF、重排和故障降级。
- 动态 Top-K 的分数断层、Parent 去重、单文档占比与上下文 Token 预算。
- Query Rewrite 次数/模型/Token/时间预算，以及引用存在性、ACL、版本和基础支持校验。
- 空/超长/重复/碎片/页码/父子关系质量门和固定评测报告比较工具。

## 当前自动验证结果

在当前工作区运行：

```text
ruff check src tests scripts       PASS
mypy src                           PASS（135 个源码文件）
pytest -q                          PASS（62 passed, 2 skipped）
uv pip check                       PASS（65 个已安装包兼容）
uv lock --check                    PASS
中英双语文档字符串审计             PASS（0 缺失、0 非双语）
```

自动测试覆盖配置、稳定 ID、内容画像、结构/语义边界、LLM 预算回退、Parent-Child、中文检索、Agent 预算、JWT/可信代理、租户范围、SQLite 持久化、删除 generation 竞态、索引状态和 HTTP 上传边界。

## 当前环境未执行

- 真实 FAISS + FastAPI + Worker 端到端测试：缺少 `faiss`，测试明确跳过。
- 真实中文 OCR 集成测试：缺少 `PyMuPDF/fitz`，测试明确跳过。
- Docker 构建与 Compose 冒烟：当前执行环境没有 Docker 命令。
- 真实 Ollama/Qwen、目标 Embedding 和 Cross-Encoder 回归：需要目标模型服务与模型缓存。
- 固定企业中文黄金集的候选/基线指标：需要项目方提供或完成授权语料标注。

这些项目是生产发布的阻断项，而不是代码单元门禁失败。应在具备对应运行时和真实评测数据的目标环境执行 `docs/DEPLOYMENT.md` 与 `docs/EVALUATION.md` 中的验收步骤。

## 残余生产风险

- 当前持久化基线是单机 SQLite 和本地不可变索引；多主机部署需要支持分布式锁/CAS 的数据库和共享对象存储适配器。
- Docker 基础镜像已固定补丁版本，但生产供应链仍应使用组织批准的镜像 digest 和 Debian 包快照。
- HS256 适合受控单体部署；跨服务身份平台建议增加 OIDC/JWKS 非对称签名适配器和密钥轮换。
- 规则与默认权重已经可配置和版本化，但最终阈值必须由固定中文黄金集调优，不能以默认值代替业务验收。
