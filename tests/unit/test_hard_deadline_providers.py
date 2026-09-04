"""中文：验证硬截止返回、有界容量和 Provider 剩余预算下推。

English: Verify hard-deadline return, bounded capacity, and provider budget propagation.
"""

from __future__ import annotations

import time
from collections.abc import Sequence

import pytest

from enterprise_rag.core.concurrency import BoundedExecutor, run_with_deadline
from enterprise_rag.core.deadline import DeadlineBudget
from enterprise_rag.core.exceptions import OperationTimeoutError
from enterprise_rag.domain.models import Chunk
from enterprise_rag.indexing.embedding_service import EmbeddingService
from enterprise_rag.retrieval.models import RetrievalCandidate
from enterprise_rag.retrieval.reranker import CandidateReranker


class _TimeoutAwareEmbedding:
    """中文：记录实际收到的向量调用超时。

    English: Record the timeout actually received by the embedding call.
    """

    fingerprint = "timeout-aware-embedding"

    def __init__(self) -> None:
        """中文：初始化未记录状态。

        English: Initialize without a recorded timeout.
        """

        self.timeout_seconds: float | None = None

    def embed(
        self,
        texts: Sequence[str],
        *,
        timeout_seconds: float | None = None,
    ) -> Sequence[Sequence[float]]:
        """中文：记录超时并返回稳定非零向量。

        English: Record timeout and return stable nonzero vectors.
        """

        self.timeout_seconds = timeout_seconds
        return tuple((1.0, float(index + 1)) for index, _ in enumerate(texts))


class _TimeoutAwareReranker:
    """中文：记录重排调用收到的剩余预算。

    English: Record the remaining budget supplied to reranking.
    """

    fingerprint = "timeout-aware-reranker"

    def __init__(self) -> None:
        """中文：初始化未记录状态。

        English: Initialize without a recorded timeout.
        """

        self.timeout_seconds: float | None = None

    def score(
        self,
        query: str,
        passages: Sequence[str],
        *,
        timeout_seconds: float | None = None,
    ) -> Sequence[float]:
        """中文：记录预算并按输入顺序返回分数。

        English: Record budget and return scores in passage order.
        """

        _ = query
        self.timeout_seconds = timeout_seconds
        return tuple(float(len(passages) - index) for index, _ in enumerate(passages))


def _chunk() -> Chunk:
    """中文：创建用于重排的最小合法 Chunk。

    English: Create a minimal valid chunk for reranking.
    """

    return Chunk(
        "chunk-a",
        "tenant-a",
        "source-a",
        "document-a",
        "version-a",
        0,
        "设备应可靠接地。",
        8,
        1,
        1,
        ("安全",),
        None,
        None,
        "document_end",
        "test-v1",
        "hash",
    )


def test_50ms_deadline_does_not_wait_for_350ms_provider() -> None:
    """中文：50ms 预算必须在容差内返回，迟到调用继续受池容量约束。

    English: A 50 ms budget returns within tolerance while late work remains capacity-bounded.
    """

    executor = BoundedExecutor(max_workers=1, queue_capacity=0, thread_name_prefix="deadline-test")
    deadline = DeadlineBudget.from_timeout(0.05)
    started = time.monotonic()

    with pytest.raises(OperationTimeoutError):
        run_with_deadline(
            executor,
            lambda: (time.sleep(0.35), "late")[1],
            deadline=deadline,
            stage="fault_provider",
        )

    assert time.monotonic() - started < 0.15
    with pytest.raises(OperationTimeoutError) as saturated:
        executor.submit(lambda: "never queued", stage="second_provider")
    assert saturated.value.detail.code == "EXECUTOR_SATURATED"
    executor.shutdown(wait=True)


def test_embedding_and_reranker_receive_remaining_budget() -> None:
    """中文：向量和重排 Provider 均收到非空、受全局预算约束的超时值。

    English: Embedding and reranking providers receive nonempty timeouts capped by global budget.
    """

    embedding_provider = _TimeoutAwareEmbedding()
    embeddings = EmbeddingService(embedding_provider, batch_size=8, expected_dimension=2)
    embeddings.embed_query("接地要求", timeout_seconds=0.25)
    assert embedding_provider.timeout_seconds == 0.25

    reranker_provider = _TimeoutAwareReranker()
    reranker = CandidateReranker(reranker_provider)
    deadline = DeadlineBudget.from_timeout(0.2)
    reranked, degraded = reranker.rerank(
        "接地要求",
        (RetrievalCandidate("chunk-a", 1.0),),
        {"chunk-a": _chunk()},
        deadline,
    )
    assert not degraded and reranked
    assert reranker_provider.timeout_seconds is not None
    assert 0.0 < reranker_provider.timeout_seconds <= 0.2
