"""中文：本模块负责实现“答案指标”相关功能。

English: Compute deterministic exact-match and token-level F1 answer metrics.
"""

from __future__ import annotations

from collections import Counter

from enterprise_rag.indexing.bm25_index import lexical_tokens


def exact_match(reference: str, prediction: str) -> float:
    """中文：该函数或方法负责“精确匹配”相关处理。

    English: Return one when normalized token sequences match exactly.
    """

    return float(lexical_tokens(reference) == lexical_tokens(prediction))


def token_f1(reference: str, prediction: str) -> float:
    """中文：该函数或方法负责“词元F1”相关处理。

    English: Return bag-of-token F1 between a reference and predicted answer.
    """

    # 中文：变量 `reference_tokens` 用于保存“`reference`词元”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Counters preserve duplicate token occurrences.
    reference_tokens = Counter(lexical_tokens(reference))
    prediction_tokens = Counter(lexical_tokens(prediction))
    if not reference_tokens and not prediction_tokens:
        return 1.0
    if not reference_tokens or not prediction_tokens:
        return 0.0
    # 中文：变量 `common` 用于保存“`common`”相关数据；其精确定义与约束见下方英文说明。
    # English: Common count uses the multiset intersection.
    common = sum((reference_tokens & prediction_tokens).values())
    precision = common / sum(prediction_tokens.values())
    recall = common / sum(reference_tokens.values())
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0
