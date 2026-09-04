"""中文：验证文档级向量预取降级和缓存生命周期。

English: Verify document-level embedding-prefetch fallback and cache lifecycle.
"""

from __future__ import annotations

from collections.abc import Sequence

from enterprise_rag.ingestion.boundary_analyzer import EmbeddingSimilarity


class _FailingEmbeddingProvider:
    """中文：模拟整批向量服务失败。

    English: Simulate a whole-batch embedding provider failure.
    """

    fingerprint = "failing-embedding-v1"

    def embed(self, _: Sequence[str]) -> Sequence[Sequence[float]]:
        """中文：对任意输入抛出提供方故障。

        English: Raise a provider failure for every input.
        """

        raise RuntimeError("provider unavailable")


class _WorkingEmbeddingProvider:
    """中文：为每段文本返回确定性二维向量。

    English: Return a deterministic two-dimensional vector for each passage.
    """

    fingerprint = "working-embedding-v1"

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """中文：根据文本长度生成稳定测试向量。

        English: Generate stable test vectors from passage length.
        """

        return tuple((float(len(value)), 1.0) for value in texts)


def test_prepare_failure_switches_the_whole_document_to_lexical() -> None:
    """中文：预取失败后所有边界统一走词法相似度且不再次调用提供方。

    English: A failed prefetch makes every boundary lexical without retrying the provider.
    """

    similarity = EmbeddingSimilarity(_FailingEmbeddingProvider())
    result = similarity.prepare(("设备应当接地", "设备不得带电维修"))

    assert result.mode == "lexical_fallback"
    assert result.failure_code == "embedding_prepare_failed"
    assert similarity.cache_size == 0
    assert similarity.similarity("设备应当接地", "设备不得带电维修") >= 0.0


def test_document_cache_is_replaced_and_released() -> None:
    """中文：连续文档不会累计向量，完成后可立即释放。

    English: Consecutive documents never accumulate vectors and can release them immediately.
    """

    similarity = EmbeddingSimilarity(_WorkingEmbeddingProvider())
    similarity.prepare(("alpha", "beta"))
    assert similarity.cache_size == 2

    similarity.prepare(("gamma",))
    assert similarity.cache_size == 1

    similarity.release_document_cache()
    assert similarity.cache_size == 0
