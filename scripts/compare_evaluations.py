"""中文：比较固定数据集的基线与 V5 候选评测报告并执行发布门禁。

English: Compare baseline and V5 candidate reports from one fixed dataset and enforce gates.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from enterprise_rag.evaluation.comparison import MetricGate, compare_reports

# 中文：检索、引用和拒答核心指标默认不得低于同数据集基线。
# English: Core retrieval, citation, and refusal metrics may not regress from the same baseline.
_DEFAULT_METRICS = (
    "hit_at_5",
    "recall_at_5",
    "mrr",
    "ndcg_at_5",
    "citation_precision",
    "citation_recall",
)


def _load_report(path: Path) -> dict[str, Any]:
    """中文：读取 JSON 对象并拒绝数组或标量报告。

    English: Load a JSON object and reject array or scalar reports.
    """

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"evaluation report must be an object: {path}")
    return payload


def main() -> None:
    """中文：解析报告和阈值，输出差值，并在任一门禁失败时返回非零退出码。

    English: Parse reports/gates, print deltas, and exit non-zero when any gate fails.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument(
        "--metric",
        action="append",
        dest="metrics",
        help="Metric gate as NAME or NAME:MINIMUM_DELTA; repeat as needed.",
    )
    arguments = parser.parse_args()
    # 中文：关键变量 `gates` 把 CLI 文本冻结成明确的指标和最小差值。
    # English: Key variable `gates` freezes CLI text into explicit metrics/minimum deltas.
    gates: list[MetricGate] = []
    for specification in arguments.metrics or _DEFAULT_METRICS:
        name, separator, raw_delta = specification.partition(":")
        gates.append(MetricGate(name, float(raw_delta) if separator else 0.0))
    result = compare_reports(
        _load_report(arguments.baseline),
        _load_report(arguments.candidate),
        tuple(gates),
    )
    print(json.dumps({"passed": result.passed, "deltas": result.deltas}, indent=2))
    if not result.passed:
        raise SystemExit("evaluation gates failed: " + ", ".join(result.failed_gates))


if __name__ == "__main__":
    main()
