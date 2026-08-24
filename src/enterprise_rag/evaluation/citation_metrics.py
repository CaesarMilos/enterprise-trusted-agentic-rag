"""中文：本模块负责实现“引用指标”相关功能。

English: Compute citation precision, recall, and claim-level completeness.
"""

from __future__ import annotations


def citation_precision(relevant: frozenset[str], cited: tuple[str, ...]) -> float:
    """中文：该函数或方法负责“引用精确率”相关处理。

    English: Return the fraction of cited chunk IDs that are relevant.
    """

    if not cited:
        return 1.0 if not relevant else 0.0
    return len(relevant & set(cited)) / len(set(cited))


def citation_recall(relevant: frozenset[str], cited: tuple[str, ...]) -> float:
    """中文：该函数或方法负责“引用召回”相关处理。

    English: Return the fraction of relevant chunks referenced by the answer.
    """

    if not relevant:
        return 1.0
    return len(relevant & set(cited)) / len(relevant)


def citation_completeness(total_claims: int, cited_claims: int) -> float:
    """中文：该函数或方法负责“引用完整度”相关处理。

    English: Return the fraction of factual claims containing at least one citation.
    """

    if total_claims <= 0:
        return 1.0
    return min(max(cited_claims, 0), total_claims) / total_claims
