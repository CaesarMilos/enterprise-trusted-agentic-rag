"""中文：本模块负责实现“运行器”相关功能。

English: Run a fixed evaluation dataset and write reproducible JSON and Markdown reports.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

from enterprise_rag.domain.results import AnswerResult, RefusalResult
from enterprise_rag.evaluation.answer_metrics import exact_match, token_f1
from enterprise_rag.evaluation.citation_metrics import citation_precision, citation_recall
from enterprise_rag.evaluation.dataset import EvaluationDataset
from enterprise_rag.evaluation.refusal_metrics import refusal_counts
from enterprise_rag.evaluation.retrieval_metrics import (
    hit_at_k,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
)
from enterprise_rag.evaluation.routing_metrics import source_precision, source_recall


@dataclass(frozen=True, slots=True)
class EvaluationPrediction:
    """中文：该类用于表示或实现“评估预测结果（EvaluationPrediction）”的职责。

    English: Represent normalized system output required by the metric runner.
    """

    # 中文：变量 `result` 用于保存“结果”相关数据；其精确定义与约束见下方英文说明。
    # English: Agent answer or refusal result.
    result: AnswerResult | RefusalResult
    # 中文：变量 `routed_source_ids` 用于保存“路由后的资料源标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Routed source IDs.
    routed_source_ids: tuple[str, ...]
    # 中文：变量 `retrieved_chunk_ids` 用于保存“`retrieved`文本块标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Ranked retrieved chunk IDs before final evidence selection.
    retrieved_chunk_ids: tuple[str, ...]
    # 中文：各排名必须来自对应 Trace 阶段，不得用最终引用代替。
    # English: Each ranking comes from its matching trace stage, never final citations.
    dense_chunk_ids: tuple[str, ...] = ()
    bm25_chunk_ids: tuple[str, ...] = ()
    fused_chunk_ids: tuple[str, ...] = ()
    reranked_chunk_ids: tuple[str, ...] = ()


class EvaluationRunner:
    """中文：该类用于表示或实现“评估运行器（EvaluationRunner）”的职责。

    English: Evaluate a fixed system callback and preserve every reproducibility fingerprint.
    """

    def __init__(
        self,
        predict: Callable[[str], EvaluationPrediction],
        fingerprints: dict[str, str],
        random_seed: int,
    ) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store the frozen prediction callback, fingerprints, and seed.
        """

        # 中文：变量 `_predict` 用于保存“`predict`”相关数据；其精确定义与约束见下方英文说明。
        # English: Callback must be pinned to one config, index, model, and prompt set.
        self._predict = predict
        # 中文：变量 `_fingerprints` 用于保存“`fingerprints`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Fingerprints are copied to prevent caller mutation during a run.
        self._fingerprints = dict(fingerprints)
        # 中文：变量 `_random_seed` 用于保存“`random``seed`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Seed is recorded even when all current metric functions are
        #   deterministic.
        self._random_seed = random_seed

    def run(self, dataset: EvaluationDataset, output_dir: Path) -> dict[str, object]:
        """中文：该函数或方法负责“运行当前流程”相关处理。

        English: Execute every example and write machine-readable and human-readable reports.
        """

        # 中文：变量 `rows` 用于保存“`rows`”相关数据；其精确定义与约束见下方英文说明。
        # English: Per-example metric rows support debugging aggregate regressions.
        rows: list[dict[str, object]] = []
        # 中文：变量 `expected_refusals` 用于保存“`expected``refusals`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Refusal labels are aggregated after all predictions.
        expected_refusals: list[bool] = []
        predicted_refusals: list[bool] = []
        for example in dataset.examples:
            prediction = self._predict(example.query)
            is_refusal = isinstance(prediction.result, RefusalResult)
            expected_refusals.append(example.should_refuse)
            predicted_refusals.append(is_refusal)
            # 中文：变量 `row` 用于保存“`row`”相关数据；其精确定义与约束见下方英文说明。
            # English: Common routing and retrieval metrics apply to answers and refusals.
            row: dict[str, object] = {
                "id": example.id,
                "source_precision": source_precision(
                    example.expected_source_ids,
                    prediction.routed_source_ids,
                ),
                "source_recall": source_recall(
                    example.expected_source_ids,
                    prediction.routed_source_ids,
                ),
                "hit_at_5": hit_at_k(
                    example.relevant_chunk_ids,
                    prediction.retrieved_chunk_ids,
                    5,
                ),
                "recall_at_5": recall_at_k(
                    example.relevant_chunk_ids,
                    prediction.retrieved_chunk_ids,
                    5,
                ),
                "mrr": reciprocal_rank(
                    example.relevant_chunk_ids,
                    prediction.retrieved_chunk_ids,
                ),
                "ndcg_at_5": ndcg_at_k(
                    example.relevant_chunk_ids,
                    prediction.retrieved_chunk_ids,
                    5,
                ),
                "dense_recall_at_5": recall_at_k(
                    example.relevant_chunk_ids,
                    prediction.dense_chunk_ids,
                    5,
                ),
                "bm25_recall_at_5": recall_at_k(
                    example.relevant_chunk_ids,
                    prediction.bm25_chunk_ids,
                    5,
                ),
                "rrf_recall_at_5": recall_at_k(
                    example.relevant_chunk_ids,
                    prediction.fused_chunk_ids,
                    5,
                ),
                "rerank_recall_at_5": recall_at_k(
                    example.relevant_chunk_ids,
                    prediction.reranked_chunk_ids,
                    5,
                ),
                "refused": is_refusal,
            }
            if isinstance(prediction.result, AnswerResult):
                # 中文：本步骤涉及答案、指标，具体约束见下方英文说明。
                # English: Answer metrics are calculated only when a reference answer
                #   exists.
                if example.reference_answer is not None:
                    row["exact_match"] = exact_match(
                        example.reference_answer,
                        prediction.result.answer,
                    )
                    row["token_f1"] = token_f1(
                        example.reference_answer,
                        prediction.result.answer,
                    )
                # 中文：变量 `cited_chunk_ids` 用于保存“`cited`文本块标识符”相关数据；
                # 其精确定义与约束见下方英文说明。
                # English: Citation metrics compare final citations with fixed relevant
                #   chunks.
                cited_chunk_ids = tuple(
                    citation.chunk_id for citation in prediction.result.citations
                )
                row["citation_precision"] = citation_precision(
                    example.relevant_chunk_ids,
                    cited_chunk_ids,
                )
                row["citation_recall"] = citation_recall(
                    example.relevant_chunk_ids,
                    cited_chunk_ids,
                )
            rows.append(row)
        # 中文：变量 `metric_names` 用于保存“指标`names`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Numeric columns are averaged only across rows containing that metric.
        metric_names = sorted(
            {
                key
                for row in rows
                for key, value in row.items()
                if isinstance(value, (int, float)) and key not in {"refused"}
            }
        )
        aggregates: dict[str, float] = {}
        for name in metric_names:
            # 中文：变量 `values` 用于保存“`values`”相关数据；其精确定义与约束见下方英文说明。
            # English: Numeric type guard narrows dynamic per-example mappings for strict
            #   typing.
            values = [
                float(value) for row in rows if isinstance((value := row.get(name)), (int, float))
            ]
            if values:
                aggregates[name] = mean(values)
        counts = refusal_counts(
            tuple(expected_refusals),
            tuple(predicted_refusals),
        )
        answerable_count = sum(not value for value in expected_refusals)
        unanswerable_count = sum(expected_refusals)
        aggregates["false_refusal_rate"] = (
            counts["false_refusal"] / answerable_count if answerable_count else 0.0
        )
        aggregates["unsafe_answer_rate"] = (
            counts["missed_refusal"] / unanswerable_count if unanswerable_count else 0.0
        )
        report: dict[str, object] = {
            "dataset": {"name": dataset.name, "version": dataset.version},
            "random_seed": self._random_seed,
            "fingerprints": self._fingerprints,
            "metrics": aggregates,
            "refusal_counts": counts,
            "examples": rows,
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        # 中文：本步骤涉及结果，具体约束见下方英文说明。
        # English: JSON contains complete reproducible results.
        (output_dir / "evaluation_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        # 中文：变量 `markdown_lines` 用于保存“Markdown`lines`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Markdown provides a compact interview-ready summary.
        markdown_lines = [
            f"# Evaluation Report: {dataset.name} {dataset.version}",
            "",
            f"- Random seed: `{self._random_seed}`",
            f"- Examples: `{len(dataset.examples)}`",
            "",
            "## Aggregate metrics",
            "",
            "| Metric | Value |",
            "|---|---:|",
        ]
        markdown_lines.extend(f"| {name} | {value:.4f} |" for name, value in aggregates.items())
        (output_dir / "evaluation_report.md").write_text(
            "\n".join(markdown_lines) + "\n",
            encoding="utf-8",
        )
        return report
