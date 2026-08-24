# V1 内容画像升级指南 / V1 Content Profile Migration

## 升级原则

- 升级前备份 `data/database`、`data/uploads` 和 `data/indexes`。
- 新版本首次启动时会为旧 `sources` 表自动增加 `content_profile` 与
  `chunk_strategy_override`，旧资料源默认使用 `general_prose`。
- 在 Admin 页面将目标 Source 更新为 `manual` 或 `technical_doc`。
- 内容画像变化后，不要只重建索引。调用
  `POST /api/v1/documents/{document_id}/reprocess` 创建新文档版本并重新切块。
- Worker 成功处理并发布新索引后，旧索引自动进入 `retired`。

## Migration rules

- Back up `data/database`, `data/uploads`, and `data/indexes` before upgrading.
- On first startup, the application adds `content_profile` and
  `chunk_strategy_override` to legacy `sources`; existing sources default to
  `general_prose`.
- Update each target Source to `manual` or `technical_doc` from the Admin page.
- A profile change requires document reprocessing, not only index rebuilding. Call
  `POST /api/v1/documents/{document_id}/reprocess` to create a new version and chunks.
- After the Worker publishes the new snapshot, the previous index becomes `retired`.

## PDF 状态 / PDF states

| 状态 / State | 含义 / Meaning |
|---|---|
| `ready` | 文本层与切块质量通过 / Text layer and chunk quality passed |
| `needs_ocr` | 扫描或混合 PDF 需要 OCR / Scanned or hybrid PDF needs OCR |
| `needs_review` | OCR 或切块质量需要人工复核 / OCR or chunk quality needs review |
| `unsupported` | 加密、损坏或明确不支持 / Encrypted, damaged, or unsupported |
