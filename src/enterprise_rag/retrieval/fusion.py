"""中文：本模块负责实现“融合”相关功能。

English: Fuse heterogeneous ranked lists with deterministic Reciprocal Rank Fusion.
"""

from __future__ import annotations

from enterprise_rag.retrieval.models import RetrievalCandidate


class ReciprocalRankFusion:
    """中文：该类用于表示或实现“倒数排名融合（ReciprocalRankFusion）”的职责。

    English: Merge dense and lexical candidates without combining incomparable raw scores.
    """

    def __init__(self, rank_constant: int = 60) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store the positive RRF rank constant.
        """

        if rank_constant < 1:
            raise ValueError("RRF rank constant must be positive")
        # 中文：变量 `_rank_constant` 用于保存“`rank``constant`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Larger constants reduce the influence of the very top rank.
        self._rank_constant = rank_constant

    def fuse(
        self,
        dense: tuple[RetrievalCandidate, ...],
        bm25: tuple[RetrievalCandidate, ...],
    ) -> tuple[RetrievalCandidate, ...]:
        """中文：该函数或方法负责“融合”相关处理。

        English: Return a deduplicated stable ranking with component provenance.
        """

        # 中文：变量 `rows` 用于保存“`rows`”相关数据；其精确定义与约束见下方英文说明。
        # English: Mutable row dictionary accumulates ranks and raw scores by stable chunk
        #   ID.
        rows: dict[str, dict[str, float | int | None]] = {}
        for candidate in dense:
            rows.setdefault(candidate.chunk_id, {})["dense_rank"] = candidate.dense_rank
            rows[candidate.chunk_id]["dense_score"] = candidate.dense_score
        for candidate in bm25:
            rows.setdefault(candidate.chunk_id, {})["bm25_rank"] = candidate.bm25_rank
            rows[candidate.chunk_id]["bm25_score"] = candidate.bm25_score
        # 中文：变量 `fused` 用于保存“`fused`”相关数据；其精确定义与约束见下方英文说明。
        # English: Fused candidates use only rank positions in the combined score.
        fused: list[RetrievalCandidate] = []
        for chunk_id, row in rows.items():
            dense_rank = _optional_int(row.get("dense_rank"))
            bm25_rank = _optional_int(row.get("bm25_rank"))
            score = sum(
                1.0 / (self._rank_constant + rank)
                for rank in (dense_rank, bm25_rank)
                if rank is not None
            )
            fused.append(
                RetrievalCandidate(
                    chunk_id=chunk_id,
                    score=score,
                    dense_rank=dense_rank,
                    bm25_rank=bm25_rank,
                    dense_score=_optional_float(row.get("dense_score")),
                    bm25_score=_optional_float(row.get("bm25_score")),
                )
            )
        # 中文：本步骤涉及标识符，具体约束见下方英文说明。
        # English: Stable ID resolves exact score ties reproducibly.
        fused.sort(key=lambda candidate: (-candidate.score, candidate.chunk_id))
        return tuple(fused)


def _optional_int(value: float | int | None) -> int | None:
    """中文：该内部函数负责“可选整数”相关处理。

    English: Convert a present numeric rank to an integer.
    """

    return None if value is None else int(value)


def _optional_float(value: float | int | None) -> float | None:
    """中文：该内部函数负责“可选浮点数”相关处理。

    English: Convert a present numeric score to a float.
    """

    return None if value is None else float(value)
