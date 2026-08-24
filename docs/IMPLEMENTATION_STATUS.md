# V0.3.0rc2 实现与验证状态

## 本轮已完成

- 文档撤销边界：在旧活动索引返回 Chunk ID 后，数据库再校验 `READY`、`active_version_id` 和资料源活动状态。
- Worker 心跳与 fencing：长时间 OCR、Embedding 和索引构建期间续租；所有持久化和发布副作用校验 `lease_owner + attempt_count + expires_at`。
- 索引发布：同租户激活事务通过租户行串行化，再完成预期活动版本 CAS。
- LLM 预算：真实请求前计数，坏 JSON、HTTP 异常与提供方失败都不能绕过每文档上限。
- 确定性回退：Embedding 异常改用本地词频余弦；LLM 异常/坏 JSON/预算耗尽改用目标长度压力。
- 上传安全：Nginx + ASGI 完整请求体上限 + 端点单文件上限三层防护。
- OCR 部署：Docker 包含 PyMuPDF、Pillow、pytesseract、Tesseract `chi_sim+eng` 和 CJK 字体。
- 删除了仍指向 `0.1.0`/DOCX 依赖的过期 `uv.lock`；当前候选版以 `pyproject.toml` 为依赖真值，待可联网的发布环境重新生成锁文件。
- 保留 V0.3 原有 PDF Reflow、内容画像、父子 Chunk、中文锚点、混合检索、Agent 问答和局部引用能力。

## 本执行环境已验证

```text
Python compileall: src / scripts / tests 全部通过
双语注释审计: 本轮修改/新增 Python 文件的模块、类、函数全部通过
100 字符行长审计: src / tests 通过
YAML 解析: default / development / docker-compose 通过
纯 Python 反例: LLM 正常上限、坏 JSON 上限、Embedding 异常回退、民法典条款、Markdown 标题、父子 Chunk 通过
```

## 必须在目标 py311 环境复验

当前容器没有 SQLAlchemy、FastAPI、Pytest、Ruff、MyPy、FAISS 和 OCR 系统依赖，因此不宣称下列门禁已在本容器通过：

```bash
python -m pip install -e ".[dev,local-models,ocr]"
python -m pytest
python -m ruff check src tests scripts
python -m mypy src
python -m pip check
docker compose config
docker compose build
```

高优先级实机验收顺序：

1. `tests/integration/test_persistence.py`：撤销边界与过期索引计划。
2. `tests/integration/test_worker_fencing.py`：租约续期、重领、旧 Worker 写入/激活拒绝。
3. `tests/integration/test_request_body_limit.py`：FastAPI multipart 413 与正常上传。
4. `tests/integration/test_real_ocr.py`：存在 Tesseract 时运行真实图像 PDF OCR。
5. `tests/e2e/test_agentic_rag_flow.py`：真实 API + Worker + FAISS/BM25 + Chat 闭环。
6. 删除后旧索引、服务重启和 Docker 网关/OCR 的部署级验收。

只有上述完整门禁在目标环境全部绿色，才能将 `0.3.0rc2` 发布为 `0.3.0`。
