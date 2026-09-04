# 部署、升级与恢复 / Deployment, upgrade, and recovery

## 开发环境

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev,local-models,ocr]"
cp .env.example .env
.venv/bin/python scripts/bootstrap_dev.py
.venv/bin/python scripts/run_all_dev.py
```

没有 `uv` 时直接使用标准 `venv + pip`。所有 Python 入口通过已安装的 src-layout 包工作，不需要 `PYTHONPATH`。Windows 可使用根目录的 `bootstrap_dev.cmd`、`run_api.cmd`、`run_worker.cmd`、`run_ui.cmd` 和 `run_all_dev.cmd`。

`bootstrap_dev` 会创建 database/uploads/indexes/traces，执行 Alembic，并幂等创建 Demo tenant/source。API 与 UI 默认使用 `127.0.0.1`，避免 localhost 代理差异。

## 生产启动

生产进程不会自动迁移数据库：启动只执行 revision 检查，不在监听端口时运行手写 DDL。部署流程必须先单独执行：

```bash
alembic -c alembic.ini upgrade head
```

然后分别运行 API、Worker 和 UI/企业前端。生产认证必须选择 JWT 或可信代理，并从 Secret 管理系统提供密钥；禁止 `authentication_mode=demo`。

## 发布与文件语义

- 索引构建写入 tenant 隔离的 `.staging` 目录。
- checksum 和重新加载验证通过后，同文件系统原子 rename 为不可变版本目录。
- 数据库 activation 使用 expected-active CAS；失败候选不会成为 runtime active。
- API/Worker 使用短事务，解析、Embedding、OCR 和索引构建不在写事务内。

## V4 → V5 升级

1. 备份数据库、uploads 和当前 active index。
2. 停止 V4 Worker，保持 API 只读或进入维护窗口。
3. 执行 `alembic upgrade head`。合法无 Alembic 的 V4 schema 可由 bootstrap/adoption 流程识别；未知 schema 会拒绝升级。
4. 启动 V5 Worker，再启动 API。
5. 验证 active index、文档 active version、任务终态和一组固定查询。
6. 暂时保留 V4 兼容读写开关；完成 Profile/Manifest 回填和 A/B 后再 contract migration。

不要直接删除 V4 字段或重写旧 Chunk ID。V5 使用 expand/migrate/contract，而不是一次性破坏性迁移。

## 备份与恢复演练

必须分别验证：

- 数据库备份能恢复 tenant、Source、DocumentVersion、Job、Snapshot 和 Revocation；
- 索引目录损坏时可从活动文档版本重建；
- 模型升级失败可回退旧配置、旧索引和旧 Provider fingerprint；
- migration 中断后数据库 revision 可诊断，不会静默继续启动；
- 删除后恢复旧备份不会使 revoked 文档重新对外可见；
- orphan staging/failed artifacts 可由 cleanup/recovery 脚本安全处理。

V0.5.0 提供构建和恢复工具，但当前工作区没有完成一次生产级备份恢复演练；后续验收报告必须记录命令、版本、耗时、校验 hash 和结果。

## 容量与可用性边界

本项目是单节点参考实现。SQLite、进程内有界执行器和本地文件索引适合受控演示和单节点验收，不等同于多副本 HA。P50/P95/P99、吞吐、最大文件/页数、RTO/RPO、资源和成本目标必须在目标硬件与目标模型上测量，不能从单元测试推断。

English summary: Development bootstraps automatically; production migrates explicitly and fails
closed on schema mismatch. Atomic local publication is implemented, while HA, DR, and capacity
claims require environment-specific evidence.
