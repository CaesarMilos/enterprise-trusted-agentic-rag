"""中文：本模块负责实现“路由指标”相关功能。

English: Compute source-routing precision and recall.
"""

from __future__ import annotations


def source_precision(expected: frozenset[str], predicted: tuple[str, ...]) -> float:
    """中文：该函数或方法负责“资料源精确率”相关处理。

    English: Return the fraction of routed sources that were expected.
    """

    # 中文：本步骤涉及资料源，具体约束见下方英文说明。
    # English: Empty prediction is correct only when no sources are expected.
    if not predicted:
        return 1.0 if not expected else 0.0
    return len(expected & set(predicted)) / len(set(predicted))


def source_recall(expected: frozenset[str], predicted: tuple[str, ...]) -> float:
    """中文：该函数或方法负责“资料源召回”相关处理。

    English: Return the fraction of expected sources present in routing output.
    """

    # 中文：本注释说明当前代码步骤的用途、约束或设计原因。
    # English: Empty expected set has complete recall by definition.
    if not expected:
        return 1.0
    return len(expected & set(predicted)) / len(expected)
