# V1 内容画像与切块策略改造记录

## 新增能力

- Source 级 `content_profile` 与可选 `chunk_strategy_override`。
- `general_prose`、`manual`、`technical_doc` 三类确定性切块策略。
- 说明书中的标题、步骤、警告、故障和参数结构识别。
- 技术文档中的标题、API、配置项、参数和代码结构保护。
- 扫描、混合、加密 PDF 分类及 `needs_ocr`、`needs_review`、`unsupported` 状态。
- 可插拔 `OCRProvider` 接口和 OCR 置信度质量门。
- Chunk 质量指标、结构类型和策略身份元数据。
- Source 内容画像管理 API 与 Streamlit 管理入口。
- 文档 `reprocess` 接口：复用原始文件创建新版本、重新切块并发布索引。
- 旧 SQLite 数据库的幂等兼容迁移。

## V1 正式支持范围

- 文件格式：文本型 PDF、Markdown、TXT。
- 内容类型：企业说明书、操作/维修手册、API/配置/运维与技术规范。
- 扫描和混合 PDF：自动识别；没有 OCR 适配器时进入 `needs_ocr`。

## 验证

- 单元与集成测试覆盖确定性切块、策略结构标注、PDF OCR 分流、SQLite
  内容画像持久化和文档重新处理。
- Ruff、Pytest、Mypy 与旧数据库迁移烟雾测试均已通过。
