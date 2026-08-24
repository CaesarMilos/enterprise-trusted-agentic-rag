"""中文：本模块负责实现“评估集”相关功能。

English: Load and validate a versioned fixed evaluation dataset.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class EvaluationExample:
    """中文：该类用于表示或实现“评估样例（EvaluationExample）”的职责。

    English: Represent one fixed question, expected evidence, answer, and refusal label.
    """

    # 中文：变量 `id` 用于保存“标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable example identifier.
    id: str
    # 中文：变量 `query` 用于保存“查询”相关数据；其精确定义与约束见下方英文说明。
    # English: Natural-language question.
    query: str
    # 中文：变量 `expected_source_ids` 用于保存“`expected`资料源标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Expected source identifiers for routing evaluation.
    expected_source_ids: frozenset[str]
    # 中文：变量 `relevant_chunk_ids` 用于保存“`relevant`文本块标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Relevant chunk identifiers for retrieval evaluation.
    relevant_chunk_ids: frozenset[str]
    # 中文：变量 `reference_answer` 用于保存“`reference`答案”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Optional reference answer for answer metrics.
    reference_answer: str | None
    # 中文：变量 `should_refuse` 用于保存“`should``refuse`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Whether the system should refuse due to insufficient authorized evidence.
    should_refuse: bool


@dataclass(frozen=True, slots=True)
class EvaluationDataset:
    """中文：该类用于表示或实现“评估评估集（EvaluationDataset）”的职责。

    English: Represent one immutable named and versioned collection of examples.
    """

    # 中文：变量 `name` 用于保存“`name`”相关数据；其精确定义与约束见下方英文说明。
    # English: Dataset name.
    name: str
    # 中文：变量 `version` 用于保存“版本”相关数据；其精确定义与约束见下方英文说明。
    # English: Explicit version recorded in reports.
    version: str
    # 中文：变量 `examples` 用于保存“`examples`”相关数据；其精确定义与约束见下方英文说明。
    # English: Ordered examples.
    examples: tuple[EvaluationExample, ...]


def load_dataset(path: Path) -> EvaluationDataset:
    """中文：该函数或方法负责“加载评估集”相关处理。

    English: Load JSON dataset content and reject missing or duplicate example identities.
    """

    # 中文：变量 `payload` 用于保存“载荷”相关数据；其精确定义与约束见下方英文说明。
    # English: Root payload contains name, version, and examples.
    payload = json.loads(path.read_text(encoding="utf-8"))
    # 中文：变量 `examples` 用于保存“`examples`”相关数据；其精确定义与约束见下方英文说明。
    # English: Examples are normalized to immutable sets.
    examples = tuple(
        EvaluationExample(
            id=str(item["id"]),
            query=str(item["query"]),
            expected_source_ids=frozenset(item.get("expected_source_ids", [])),
            relevant_chunk_ids=frozenset(item.get("relevant_chunk_ids", [])),
            reference_answer=item.get("reference_answer"),
            should_refuse=bool(item.get("should_refuse", False)),
        )
        for item in payload["examples"]
    )
    # 中文：本注释说明当前代码步骤的用途、约束或设计原因。
    # English: Duplicate IDs would silently corrupt per-example report joins.
    if len({example.id for example in examples}) != len(examples):
        raise ValueError("evaluation dataset contains duplicate example IDs")
    if not payload.get("name") or not payload.get("version"):
        raise ValueError("evaluation dataset requires name and version")
    return EvaluationDataset(str(payload["name"]), str(payload["version"]), examples)
