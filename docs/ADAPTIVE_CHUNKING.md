# V4 自适应中文边界与 Parent-Child 切块

## 目标

切块算法必须同时满足：不跨越业务硬边界、在软边界处利用语义连续性、长度受控、结果可解释且相同输入可复现。LLM 只作为模糊候选的可选复核器，不拥有最终结构解释权。

## 输入流水线

1. Loader 逐页读取 PDF 或读取 Markdown/TXT。
2. OCR 补齐没有可靠文本层的页面，任何缺页或低置信度页阻止发布。
3. Cleaner 恢复 PDF 视觉断行、去除重复页眉页脚并保留页码。
4. `ContentProfiler` 结合 Source 配置和确定性结构信号选择画像；低置信度回退 `general_prose`。
5. `StructureParser` 与画像规则生成标题、条款、步骤、警告、表格、代码和段落等最小语义单元。
6. `ChineseSentenceSplitter` 在必须拆分长单元时保护小数、版本号、URL、中英文引号和括号。

## 六类内容画像

| 画像 | 核心结构 | 主要保护规则 |
|---|---|---|
| `general_prose` | 标题、段落、句子 | 不跨标题，保守合并 |
| `manual` | 步骤、警告、参数、故障 | 警告与普通步骤分离 |
| `technical_doc` | API、配置、代码、参数 | 代码/API 块保护 |
| `regulation` | 章、节、条、款、项 | 不跨条文合并 |
| `academic` | 摘要、章节、引用列表 | 同小节语义合并 |
| `narrative` | 章节、场景、自然段 | 允许同场景相邻段落合并 |

## 硬边界优先

候选位置满足下列任一条件时直接切分，不参与分数阈值：新标题或标题路径变化、法规条款、画像声明的受保护结构、超过 `max_tokens`。仅含标题的缓冲区会吸附下一正文，避免产生孤立标题块。

## 五特征边界评分

对非硬边界计算：

$$
B_i = w_sS_i + w_eG_i + w_lL_i + w_mM_i + w_rR_i
$$

| 特征 | 含义 | 当前来源 |
|---|---|---|
| $S_i$ | 软结构变化强度 | 相邻最小单元类型 |
| $G_i$ | 语义间隙 | $(1-\text{cosine})/2$ |
| $L_i$ | 长度压力 | 当前块从 `min` 到 `max` 的归一化进度 |
| $M_i$ | 标记变化 | 条款编号、标题路径、页码 |
| $R_i$ | 语义角色变化 | 正文、步骤、警告、表格、代码等 |

默认权重为 `0.30/0.30/0.20/0.10/0.10`，总和必须严格为一，并冻结到 `DocumentVersion.chunk_parameters_json`。语义相似度使用“上一单元相似度”和“当前缓冲区向量质心相似度”的组合，既响应局部话题转折，也避免单个短句抖动。

## 动态阈值

基础阈值默认为 `0.58`：

- 小于 `min_tokens`：阈值提高，抑制碎片化。
- `min_tokens` 到 `target_tokens`：阈值逐步回到基础值。
- `target_tokens` 到 `max_tokens`：阈值线性降低，使长块更易在合理位置结束。
- 加入下一单元会超过 `max_tokens`：强制在安全位置切分。

当 $B_i \ge T(n)$ 时切分，否则合并。每个 Chunk 元数据保存 `boundary_score`、`boundary_threshold`、五项特征、语义相似度、方法和置信度，Trace 因此可以解释决策。

## LLM 模糊边界复核

只有 `abs(score-threshold) <= semantic_ambiguity_margin` 且功能开启时才调用 LLM。调用预算在请求前计数；异常、坏 JSON 和预算耗尽都回退加权分数，并记录 `llm_provider_error`、`llm_invalid_json` 或 `llm_budget_exhausted`。关闭 LLM 不会关闭自适应算法。

## 过长、过短和重叠

- 过长单元按结构、段落、中文句子和安全字符跨度依次拆分。
- 过短块只能在相同父结构、相同受保护角色且不超过最大 Token 时合并。
- 检索重叠采用上一个块的完整末句，只写入 `retrieval_text`；`body_text` 和引用正文不重复。
- 标题路径写入 `retrieval_text`，提高 BM25/Embedding 命中，但引用展示原始正文。

## Parent-Child

叶子 Child 按源文顺序生成稳定 ID，并进入 BM25 与向量索引。相同结构父键的 Child 聚合为 Parent，Parent 保存 `child_chunk_ids`，Child 保存 `parent_chunk_id`。质量门验证关系双向闭合。

在线检索只返回 Child。`ParentExpander` 验证 Parent 与 Child 同租户、Source、文档和不可变版本，并同时受 `max_parent_tokens` 与总上下文预算约束。答案上下文可以使用 Parent，但引用 ID、页码和摘录仍来自 Child。

## 保守回退

无法可靠识别结构或内容画像时执行：段落优先、中文句子安全切割、固定最大 Token、完整句有限重叠、不跨标题。向量服务失败时使用确定性词频余弦；所有回退原因进入版本质量指标和 Chunk 元数据。

## 发布门禁

- 空 Chunk、超长 Child、倒置页码、重复 ID：阻止发布。
- Parent 缺失或父子关系不互指：阻止发布。
- 极端碎片化或重复内容：达到严重阈值时阻止发布，否则告警。
- 相同输入和快照重复执行的稳定 ID、顺序、哈希、父子映射一致率必须为 `1.0`。
- 固定黄金集的硬边界违反率必须为零。
