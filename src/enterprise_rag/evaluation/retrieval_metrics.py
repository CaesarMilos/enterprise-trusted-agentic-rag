"""中文：本模块负责实现“检索指标”相关功能。

English: Compute standard ranked retrieval metrics for fixed relevant chunk sets.
"""

from __future__ import annotations

import math


def hit_at_k(relevant: frozenset[str], ranked: tuple[str, ...], k: int) -> float:
    """中文：该函数或方法负责“命中按K 值”相关处理。

    English: Return one when any relevant chunk appears in the first K results.
    """

    return float(bool(relevant & set(ranked[:k])))


def recall_at_k(relevant: frozenset[str], ranked: tuple[str, ...], k: int) -> float:
    """中文：该函数或方法负责“召回按K 值”相关处理。

    English: Return the fraction of relevant chunks retrieved in the first K results.
    """

    if not relevant:
        return 1.0
    return len(relevant & set(ranked[:k])) / len(relevant)


def reciprocal_rank(relevant: frozenset[str], ranked: tuple[str, ...]) -> float:
    """中文：该函数或方法负责“倒数排名”相关处理。

    English: Return the reciprocal rank of the first relevant chunk.
    """

    for rank, chunk_id in enumerate(ranked, start=1):
        if chunk_id in relevant:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(relevant: frozenset[str], ranked: tuple[str, ...], k: int) -> float:
    """中文：该函数或方法负责“nDCG按K 值”相关处理。

    English: Return binary-relevance normalized discounted cumulative gain at K.
    """

    # 中文：变量 `dcg` 用于保存“`dcg`”相关数据；其精确定义与约束见下方英文说明。
    # English: DCG discounts each relevant rank logarithmically.
    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, chunk_id in enumerate(ranked[:k], start=1)
        if chunk_id in relevant
    )
    # 中文：变量 `ideal_count` 用于保存“`ideal``count`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Ideal list contains as many relevant items as fit within K.
    ideal_count = min(len(relevant), k)
    ideal_dcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_count + 1))
    return dcg / ideal_dcg if ideal_dcg else 1.0
