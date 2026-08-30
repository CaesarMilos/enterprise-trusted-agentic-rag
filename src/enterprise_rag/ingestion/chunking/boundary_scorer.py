"""中文：实现 V4 可解释、可复现的多特征自适应边界评分算法。

English: Implement V4's explainable and reproducible multi-feature adaptive boundary scorer.
"""

from __future__ import annotations

from dataclasses import dataclass


def _unit_interval(value: float) -> float:
    """中文：把任意有限特征值限制在零到一，防止单项权重支配总分。

    English: Clamp a finite feature to zero-one so one signal cannot dominate the score.
    """

    return max(0.0, min(1.0, value))


@dataclass(frozen=True, slots=True)
class BoundaryWeights:
    """中文：冻结结构、语义、长度、标记和角色变化五项权重。

    English: Freeze weights for structure, semantic gap, length, marker, and role change.
    """

    structure: float = 0.30
    semantic_gap: float = 0.30
    length_pressure: float = 0.20
    marker_change: float = 0.10
    role_change: float = 0.10

    def __post_init__(self) -> None:
        """中文：要求非负权重之和严格等于一，保证配置含义稳定。

        English: Require non-negative weights summing to one for stable configuration meaning.
        """

        values = (
            self.structure,
            self.semantic_gap,
            self.length_pressure,
            self.marker_change,
            self.role_change,
        )
        if any(value < 0.0 for value in values) or abs(sum(values) - 1.0) > 1e-6:
            raise ValueError("boundary weights must be non-negative and sum to 1.0")


@dataclass(frozen=True, slots=True)
class BoundaryFeatures:
    """中文：保存候选边界的五项标准化特征，供 Trace 与离线评测解释。

    English: Store five normalized candidate features for traces and offline evaluation.
    """

    structural_strength: float
    semantic_gap: float
    length_pressure: float
    marker_change: float
    role_change: float

    def normalized(self) -> BoundaryFeatures:
        """中文：返回全部限制在零到一范围内的不可变特征副本。

        English: Return an immutable copy with every feature clamped to zero-one.
        """

        return BoundaryFeatures(
            structural_strength=_unit_interval(self.structural_strength),
            semantic_gap=_unit_interval(self.semantic_gap),
            length_pressure=_unit_interval(self.length_pressure),
            marker_change=_unit_interval(self.marker_change),
            role_change=_unit_interval(self.role_change),
        )


@dataclass(frozen=True, slots=True)
class BoundaryScore:
    """中文：记录加权总分、动态阈值和最终是否切分。

    English: Record weighted score, dynamic threshold, and the resulting split decision.
    """

    score: float
    threshold: float
    should_split: bool
    features: BoundaryFeatures


class AdaptiveBoundaryScorer:
    """中文：依据长度区间动态调整阈值，再对多特征总分做确定性判断。

    English: Shift the threshold by length region and deterministically evaluate feature score.
    """

    def __init__(
        self,
        *,
        min_tokens: int,
        target_tokens: int,
        max_tokens: int,
        base_threshold: float = 0.58,
        weights: BoundaryWeights | None = None,
    ) -> None:
        """中文：校验 Token 区间和基础阈值，并冻结评分参数。

        English: Validate token bounds/base threshold and freeze scoring parameters.
        """

        if not 1 <= min_tokens <= target_tokens <= max_tokens:
            raise ValueError("token bounds must satisfy 1 <= min <= target <= max")
        if not 0.0 <= base_threshold <= 1.0:
            raise ValueError("base boundary threshold must be within zero and one")
        self._min_tokens = min_tokens
        self._target_tokens = target_tokens
        self._max_tokens = max_tokens
        self._base_threshold = base_threshold
        self._weights = weights or BoundaryWeights()

    def length_pressure(self, token_count: int) -> float:
        """中文：把当前块长度映射为零到一压力，达到 max 时为一。

        English: Map current chunk length to zero-one pressure, reaching one at max tokens.
        """

        if token_count <= self._min_tokens:
            return 0.0
        span = max(1, self._max_tokens - self._min_tokens)
        return _unit_interval((token_count - self._min_tokens) / span)

    def dynamic_threshold(self, token_count: int) -> float:
        """中文：短块提高切分门槛，超过目标后线性降低，max 由硬规则强制切分。

        English: Raise the threshold for short chunks and lower it linearly after the target.
        """

        if token_count < self._min_tokens:
            return min(0.90, self._base_threshold + 0.22)
        if token_count <= self._target_tokens:
            progress = (token_count - self._min_tokens) / max(
                1, self._target_tokens - self._min_tokens
            )
            return self._base_threshold + 0.10 * (1.0 - progress)
        progress = (token_count - self._target_tokens) / max(
            1, self._max_tokens - self._target_tokens
        )
        return max(0.30, self._base_threshold - 0.24 * progress)

    def score(self, features: BoundaryFeatures, token_count: int) -> BoundaryScore:
        """中文：计算公式 B=wsS+weG+wlL+wmM+wrR，并与动态阈值比较。

        English: Compute B=wsS+weG+wlL+wmM+wrR and compare it with the dynamic threshold.
        """

        normalized = features.normalized()
        weighted = (
            self._weights.structure * normalized.structural_strength
            + self._weights.semantic_gap * normalized.semantic_gap
            + self._weights.length_pressure * normalized.length_pressure
            + self._weights.marker_change * normalized.marker_change
            + self._weights.role_change * normalized.role_change
        )
        threshold = self.dynamic_threshold(token_count)
        return BoundaryScore(
            score=weighted,
            threshold=threshold,
            should_split=weighted >= threshold,
            features=normalized,
        )
