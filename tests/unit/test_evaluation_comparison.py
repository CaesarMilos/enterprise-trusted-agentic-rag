"""中文：验证同数据集候选报告的准确率回归门禁。

English: Verify accuracy-regression gates for candidate reports on one dataset.
"""

import pytest

from enterprise_rag.evaluation.comparison import MetricGate, compare_reports


def test_comparison_requires_metric_non_regression() -> None:
    """中文：任一指标低于允许差值时都必须阻止候选发布。

    English: Any metric below its permitted delta must block candidate publication.
    """

    baseline = {
        "dataset": {"name": "golden-zh", "version": "1"},
        "metrics": {"recall_at_5": 0.80, "mrr": 0.70},
    }
    candidate = {
        "dataset": {"name": "golden-zh", "version": "1"},
        "metrics": {"recall_at_5": 0.85, "mrr": 0.69},
    }

    result = compare_reports(
        baseline,
        candidate,
        (MetricGate("recall_at_5"), MetricGate("mrr")),
    )

    assert not result.passed
    assert result.deltas == pytest.approx({"recall_at_5": 0.05, "mrr": -0.01})
    assert result.failed_gates == ("mrr:-0.010000<0.000000",)
