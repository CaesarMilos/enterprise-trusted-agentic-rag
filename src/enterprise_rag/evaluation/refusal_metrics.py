"""中文：本模块负责实现“拒答指标”相关功能。

English: Compute correct, false, and missed refusal rates.
"""

from __future__ import annotations


def refusal_counts(
    expected_refusals: tuple[bool, ...],
    predicted_refusals: tuple[bool, ...],
) -> dict[str, int]:
    """中文：该函数或方法负责“拒答计数”相关处理。

    English: Return a confusion-style count mapping for refusal behavior.
    """

    if len(expected_refusals) != len(predicted_refusals):
        raise ValueError("refusal label arrays must have the same length")
    # 中文：变量 `labels` 用于保存“标签”相关数据；其精确定义与约束见下方英文说明。
    # English: Correct refusal means an unanswerable case was refused.
    labels = zip(expected_refusals, predicted_refusals, strict=True)
    correct = sum(expected and predicted for expected, predicted in labels)
    # 中文：变量 `labels` 用于保存“标签”相关数据；其精确定义与约束见下方英文说明。
    # English: False refusal means an answerable case was refused.
    labels = zip(expected_refusals, predicted_refusals, strict=True)
    false = sum(not expected and predicted for expected, predicted in labels)
    # 中文：变量 `labels` 用于保存“标签”相关数据；其精确定义与约束见下方英文说明。
    # English: Missed refusal means an unanswerable case received an answer.
    labels = zip(expected_refusals, predicted_refusals, strict=True)
    missed = sum(expected and not predicted for expected, predicted in labels)
    return {"correct_refusal": correct, "false_refusal": false, "missed_refusal": missed}
