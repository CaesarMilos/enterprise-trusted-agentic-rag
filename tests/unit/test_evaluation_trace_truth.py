"""中文：验证评测读取真实检索层级，并在拒答后保留排名。

English: Verify evaluation reads real retrieval stages and preserves rankings after refusal.
"""

from pathlib import Path

from enterprise_rag.core.enums import RefusalReason
from enterprise_rag.domain.results import RefusalResult
from enterprise_rag.evaluation.dataset import EvaluationDataset, EvaluationExample
from enterprise_rag.evaluation.runner import EvaluationPrediction, EvaluationRunner
from enterprise_rag.retrieval.models import RankedCandidateTrace, RetrievalTrace


def test_refusal_metrics_use_real_stage_rankings(tmp_path: Path) -> None:
    """中文：最终拒答不得擦除 Dense/RRF 排名，也不得用 Citation 冒充检索结果。

    English: Final refusal cannot erase Dense/RRF ranks or replace retrieval with citations.
    """

    # 中文：关键变量 `trace` 故意让不同阶段结果不同，以发现错误的数据层级复用。
    # English: Key variable `trace` intentionally differs by stage to expose proxy reuse.
    trace = RetrievalTrace(
        routed_source_ids=("source-a",),
        dense=(RankedCandidateTrace("relevant", 1, 1.0),),
        bm25=(RankedCandidateTrace("irrelevant", 1, 1.0),),
        fused=(RankedCandidateTrace("relevant", 1, 1.0),),
        reranked=(RankedCandidateTrace("irrelevant", 1, 1.0),),
    )
    refusal = RefusalResult(
        trace_id="trace-a",
        reason=RefusalReason.INSUFFICIENT_EVIDENCE,
        message="Insufficient evidence.",
        index_version_id="index-a",
        retrieval_trace=trace,
    )
    prediction = EvaluationPrediction(
        result=refusal,
        routed_source_ids=trace.routed_source_ids,
        retrieved_chunk_ids=("irrelevant",),
        dense_chunk_ids=("relevant",),
        bm25_chunk_ids=("irrelevant",),
        fused_chunk_ids=("relevant",),
        reranked_chunk_ids=("irrelevant",),
    )
    dataset = EvaluationDataset(
        name="trace-truth",
        version="1",
        examples=(
            EvaluationExample(
                id="answerable-refused",
                query="What is the rule?",
                expected_source_ids=frozenset({"source-a"}),
                relevant_chunk_ids=frozenset({"relevant"}),
                reference_answer=None,
                should_refuse=False,
            ),
        ),
    )
    runner = EvaluationRunner(lambda query: prediction, {"code": "test"}, random_seed=7)

    report = runner.run(dataset, tmp_path / "report")

    metrics = report["metrics"]
    assert isinstance(metrics, dict)
    assert metrics["dense_recall_at_5"] == 1.0
    assert metrics["bm25_recall_at_5"] == 0.0
    assert metrics["rrf_recall_at_5"] == 1.0
    assert metrics["rerank_recall_at_5"] == 0.0
    assert metrics["false_refusal_rate"] == 1.0
