"""中文：比较固定评测集的基线与候选报告，并执行 V4 质量回归门禁。

English: Compare baseline and candidate reports and enforce V4 quality-regression gates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class MetricGate:
    """中文：描述单个指标允许的最小变化量，正值表示必须提升。

    English: Describe one metric's minimum permitted delta; positive values require improvement.
    """

    # 中文：指标名必须与评测报告 `metrics` 字段一致。
    # English: Metric name must match a key under the report's `metrics` object.
    name: str
    # 中文：候选值减基线值的最小允许差值。
    # English: Minimum allowed candidate-minus-baseline delta.
    minimum_delta: float = 0.0


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    """中文：保存各指标差值、失败门禁和最终是否可发布。

    English: Hold metric deltas, failed gates, and the final publication decision.
    """

    deltas: dict[str, float]
    failed_gates: tuple[str, ...]

    @property
    def passed(self) -> bool:
        """中文：仅当所有配置门禁都满足时允许候选版本发布。

        English: Allow candidate publication only when every configured gate passes.
        """

        return not self.failed_gates


def compare_reports(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    gates: tuple[MetricGate, ...],
) -> ComparisonResult:
    """中文：要求相同数据集版本，并按候选减基线计算稳定指标差值。

    English: Require one dataset version and compute stable candidate-minus-baseline deltas.
    """

    if baseline.get("dataset") != candidate.get("dataset"):
        raise ValueError("evaluation reports must use the same dataset and version")
    baseline_metrics = baseline.get("metrics")
    candidate_metrics = candidate.get("metrics")
    if not isinstance(baseline_metrics, dict) or not isinstance(candidate_metrics, dict):
        raise ValueError("evaluation reports require metric mappings")

    deltas: dict[str, float] = {}
    failed: list[str] = []
    for gate in gates:
        baseline_value = baseline_metrics.get(gate.name)
        candidate_value = candidate_metrics.get(gate.name)
        if not isinstance(baseline_value, (int, float)) or not isinstance(
            candidate_value, (int, float)
        ):
            failed.append(f"{gate.name}:missing")
            continue
        delta = float(candidate_value) - float(baseline_value)
        deltas[gate.name] = delta
        if delta < gate.minimum_delta:
            failed.append(f"{gate.name}:{delta:.6f}<{gate.minimum_delta:.6f}")
    return ComparisonResult(deltas, tuple(failed))
