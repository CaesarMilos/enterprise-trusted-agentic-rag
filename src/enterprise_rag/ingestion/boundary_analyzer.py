"""中文：本模块融合结构规则、向量相似度与可选 LLM 判断，生成可审计的切块边界。

English: Combine structural rules, embedding similarity, and optional LLM review to produce
auditable chunk-boundary decisions.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Protocol, Sequence

from enterprise_rag.domain.protocols.models import EmbeddingProvider, LLMProvider
from enterprise_rag.ingestion.structure_parser import StructuredUnit

# 中文：中文单字和拉丁词项构成无外部模型时的确定性语义回退向量。
# English: CJK characters and Latin terms form deterministic fallback vectors.
_TERM_PATTERN = re.compile(r"[\u3400-\u9fff]|[A-Za-z0-9_]{2,}")


@dataclass(frozen=True, slots=True)
class BoundaryDecision:
    """中文：描述一个候选位置是否切分及其算法来源和置信度。

    English: Describe whether a candidate position should split and record its method and
    confidence.
    """

    # 中文：`should_split` 表示应在右侧单元之前提交当前缓冲区。
    # English: `should_split` commits the current buffer before the right-hand unit.
    should_split: bool
    # 中文：`method` 是可用于审计和评估的稳定判定标签。
    # English: `method` is a stable label used by audits and evaluation.
    method: str
    # 中文：`confidence` 为零到一之间的判定可信度。
    # English: `confidence` is the decision certainty in the inclusive zero-to-one range.
    confidence: float
    # 中文：`similarity` 保存实际语义相似度；未计算时为空。
    # English: `similarity` stores the semantic score and is absent when not computed.
    similarity: float | None = None
    # 中文：`llm_attempted` 表示当前候选位置是否真实发起过模型复核。
    # English: `llm_attempted` records whether this candidate made a real model request.
    llm_attempted: bool = False
    # 中文：`fallback_reason` 保存外部模型失效或预算耗尽的稳定审计标签。
    # English: `fallback_reason` stores a stable audit label for provider or budget fallback.
    fallback_reason: str | None = None
    # 中文：`llm_calls_used` 保存当前文档截至本次判定消耗的真实调用次数。
    # English: `llm_calls_used` stores real document-level calls consumed by this decision.
    llm_calls_used: int = 0


@dataclass(slots=True)
class BoundaryReviewBudget:
    """中文：按真实模型请求次数限制单文档 LLM 边界复核成本。

    English: Limit document-level LLM boundary cost by real provider requests.
    """

    # 中文：变量 `maximum_calls` 是单文档允许发起的模型请求硬上限。
    # English: `maximum_calls` is the hard per-document provider-request cap.
    maximum_calls: int
    # 中文：变量 `used_calls` 在请求前递增，因此坏 JSON 和异常同样计费。
    # English: `used_calls` increments before requests, so invalid JSON and errors count.
    used_calls: int = 0

    def __post_init__(self) -> None:
        """中文：拒绝负数预算和不一致的初始调用计数。

        English: Reject negative budgets and inconsistent initial usage.
        """

        if self.maximum_calls < 0:
            raise ValueError("maximum boundary review calls cannot be negative")
        if not 0 <= self.used_calls <= self.maximum_calls:
            raise ValueError("used boundary review calls must be within the configured budget")

    @property
    def remaining_calls(self) -> int:
        """中文：返回当前文档仍可发起的模型请求数量。

        English: Return the remaining provider requests available to the document.
        """

        return self.maximum_calls - self.used_calls

    def try_acquire(self) -> bool:
        """中文：在真实请求之前原子式消耗一次本地预算。

        English: Consume one local budget unit immediately before a real request.
        """

        if self.used_calls >= self.maximum_calls:
            return False
        self.used_calls += 1
        return True


class SimilarityProvider(Protocol):
    """中文：定义切块边界分析器所需的最小文本相似度接口。

    English: Define the minimal text-similarity interface required by boundary analysis.
    """

    def similarity(self, left: str, right: str) -> float:
        """中文：返回两段文本的余弦相似度。

        English: Return cosine similarity between two passages.
        """


class EmbeddingSimilarity:
    """中文：使用统一向量提供方计算切块候选位置的语义连续性。

    English: Use the configured embedding provider to measure semantic continuity at a
    candidate boundary.
    """

    def __init__(self, provider: EmbeddingProvider) -> None:
        """中文：保存与在线索引一致的向量提供方。

        English: Store the same embedding provider used by the online index.
        """

        # 中文：关键变量 `_provider` 负责批量生成左右文本向量。
        # English: Key variable `_provider` embeds the left and right passages in one batch.
        self._provider = provider

    def similarity(self, left: str, right: str) -> float:
        """中文：计算左右文本向量的安全余弦相似度。

        English: Compute a numerically safe cosine similarity for the two passages.
        """

        vectors = self._provider.embed((left, right))
        if len(vectors) != 2:
            return 0.0
        return _vector_cosine(vectors[0], vectors[1])


class LLMBoundaryJudge:
    """中文：仅在算法分数模糊时，请 LLM 对局部上下文做受约束的边界复核。

    English: Ask an LLM to review bounded local context only when deterministic scores are
    ambiguous.
    """

    prompt_version = "boundary-json-v1"

    def __init__(self, provider: LLMProvider, max_context_chars: int = 1800) -> None:
        """中文：保存模型提供方与单次复核的最大局部字符数。

        English: Store the model provider and the maximum local context supplied per review.
        """

        self._provider = provider
        self._max_context_chars = max_context_chars

    @property
    def fingerprint(self) -> str:
        """中文：返回模型与提示词版本组成的可审计指纹。

        English: Return an auditable model-and-prompt fingerprint.
        """

        return f"{self._provider.fingerprint}:{self.prompt_version}"

    def decide(self, left: str, right: str) -> BoundaryDecision | None:
        """中文：要求模型只返回 JSON，并在解析失败时安全回退。

        English: Require JSON-only output and fail safely to deterministic logic when parsing
        fails.
        """

        # 中文：局部片段从边界两侧截取，避免将整份文档发送给模型。
        # English: Local excerpts are clipped around the boundary instead of sending the file.
        half = self._max_context_chars // 2
        response = self._provider.complete(
            "你是文档结构边界判定器。只输出 JSON，不回答文档内容。/ "
            "You are a document boundary classifier. Return JSON only.",
            (
                '判断 RIGHT 是否开启独立主题或结构块。返回 '
                '{"split":true|false,"confidence":0..1}。\n'
                f"LEFT:\n{left[-half:]}\n\nRIGHT:\n{right[:half]}"
            ),
            {"task": "ingestion_boundary", "prompt_version": self.prompt_version},
        )
        try:
            payload = json.loads(_extract_json(response.text))
            should_split = payload["split"]
            confidence = float(payload["confidence"])
            if not isinstance(should_split, bool) or not math.isfinite(confidence):
                return None
            return BoundaryDecision(
                should_split=should_split,
                method="llm_boundary",
                confidence=max(0.0, min(1.0, confidence)),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None


class AdaptiveBoundaryAnalyzer:
    """中文：按“硬结构→长度→向量→LLM→确定性回退”的顺序选择切块边界。

    English: Select boundaries in the order hard structure, length, embeddings, LLM review,
    and deterministic fallback.
    """

    def __init__(
        self,
        *,
        min_tokens: int,
        target_tokens: int,
        max_tokens: int,
        hard_boundary_kinds: frozenset[str],
        semantic_threshold: float = 0.52,
        ambiguity_margin: float = 0.08,
        similarity_provider: SimilarityProvider | None = None,
        llm_judge: LLMBoundaryJudge | None = None,
    ) -> None:
        """中文：校验预算并保存自适应边界判定依赖。

        English: Validate token budgets and store adaptive boundary-analysis dependencies.
        """

        if not 1 <= min_tokens <= target_tokens <= max_tokens:
            raise ValueError("chunk bounds must satisfy 1 <= min <= target <= max")
        self._min_tokens = min_tokens
        self._target_tokens = target_tokens
        self._max_tokens = max_tokens
        self._hard_boundary_kinds = hard_boundary_kinds
        self._semantic_threshold = semantic_threshold
        self._ambiguity_margin = ambiguity_margin
        self._similarity = similarity_provider
        self._llm_judge = llm_judge

    def decide(
        self,
        buffer: Sequence[StructuredUnit],
        buffer_tokens: int,
        right: StructuredUnit,
        *,
        review_budget: BoundaryReviewBudget | None = None,
    ) -> BoundaryDecision:
        """中文：对右侧单元前的候选位置生成一次可解释的边界判定。

        English: Produce one explainable decision for the candidate position before the right
        unit.
        """

        if not buffer:
            return BoundaryDecision(False, "document_start", 1.0)
        if buffer_tokens + right.token_count > self._max_tokens:
            return BoundaryDecision(True, "max_tokens", 1.0)
        # 中文：标题单元应作为下一正文块的检索前缀，不能被强边界切成孤立微块。
        # English: Heading-only buffers prefix the following body and should not become isolated
        # micro-chunks at a hard boundary.
        if all(unit.kind == "heading" for unit in buffer):
            return BoundaryDecision(False, "heading_prefix", 1.0)
        if right.kind in self._hard_boundary_kinds or right.kind in {
            "heading",
            "numbered_clause",
        }:
            return BoundaryDecision(True, "structural_boundary", 1.0)
        if right.heading_path != buffer[-1].heading_path:
            return BoundaryDecision(True, "heading_change", 1.0)
        if buffer_tokens < self._min_tokens:
            return BoundaryDecision(False, "below_min_tokens", 1.0)
        if buffer_tokens < self._target_tokens:
            return BoundaryDecision(False, "below_target_tokens", 0.9)

        # 中文：检索文本包含标题和编号，比只看正文更适合识别说明书/法典边界。
        # English: Retrieval text includes headings and identifiers, improving manual/legal
        # boundary signals.
        left_text = buffer[-1].retrieval_text or buffer[-1].text
        right_text = right.retrieval_text or right.text
        # 中文：关键变量 `similarity_fallback` 记录向量提供方异常后的词频降级。
        # English: Key variable `similarity_fallback` records lexical degradation after a
        # similarity-provider error.
        similarity_fallback: str | None = None
        if self._similarity is None:
            similarity = _lexical_cosine(left_text, right_text)
        else:
            try:
                similarity = self._similarity.similarity(left_text, right_text)
                if not math.isfinite(similarity):
                    raise ValueError("similarity provider returned a non-finite value")
                similarity = max(-1.0, min(1.0, similarity))
            except Exception:
                # 中文：外部向量异常不能终止文档切块，回退算法不依赖任何外部服务。
                # English: External similarity failures cannot abort chunking; lexical cosine
                # has no provider dependency.
                similarity = _lexical_cosine(left_text, right_text)
                similarity_fallback = "embedding_provider_error"
        lower = self._semantic_threshold - self._ambiguity_margin
        upper = self._semantic_threshold + self._ambiguity_margin
        if similarity <= lower:
            return BoundaryDecision(
                True,
                "lexical_fallback_gap" if similarity_fallback else "semantic_gap",
                1.0 - max(0.0, similarity),
                similarity,
                fallback_reason=similarity_fallback,
            )
        if similarity >= upper:
            return BoundaryDecision(
                False,
                "lexical_fallback_continuity" if similarity_fallback else "semantic_continuity",
                similarity,
                similarity,
                fallback_reason=similarity_fallback,
            )
        llm_fallback_reason: str | None = similarity_fallback
        llm_attempted = False
        if self._llm_judge is not None and review_budget is not None:
            if review_budget.try_acquire():
                llm_attempted = True
                try:
                    reviewed = self._llm_judge.decide(left_text, right_text)
                except Exception:
                    reviewed = None
                    llm_fallback_reason = "llm_provider_error"
                if reviewed is not None:
                    return BoundaryDecision(
                        reviewed.should_split,
                        reviewed.method,
                        reviewed.confidence,
                        similarity,
                        llm_attempted=True,
                        fallback_reason=similarity_fallback,
                        llm_calls_used=review_budget.used_calls,
                    )
                if llm_fallback_reason != "llm_provider_error":
                    llm_fallback_reason = "llm_invalid_json"
            else:
                llm_fallback_reason = "llm_budget_exhausted"
        # 中文：模糊区回退到目标长度压力，确保关闭 LLM 时结果仍可复现。
        # English: The ambiguous band falls back to size pressure for reproducibility without
        # an LLM.
        should_split = buffer_tokens >= int(self._target_tokens * 1.2)
        fallback_method = {
            "llm_provider_error": "llm_provider_error_fallback",
            "llm_invalid_json": "llm_invalid_json_fallback",
            "llm_budget_exhausted": "llm_budget_exhausted",
        }.get(llm_fallback_reason, "size_pressure")
        return BoundaryDecision(
            should_split,
            fallback_method,
            0.6,
            similarity,
            llm_attempted=llm_attempted,
            fallback_reason=llm_fallback_reason,
            llm_calls_used=review_budget.used_calls if review_budget is not None else 0,
        )


def _lexical_cosine(left: str, right: str) -> float:
    """中文：计算字符/词频余弦，作为向量服务不可用时的确定性回退。

    English: Compute term-frequency cosine as the deterministic embedding fallback.
    """

    left_terms = Counter(term.lower() for term in _TERM_PATTERN.findall(left))
    right_terms = Counter(term.lower() for term in _TERM_PATTERN.findall(right))
    if not left_terms or not right_terms:
        return 0.0
    dot_product = sum(value * right_terms.get(term, 0) for term, value in left_terms.items())
    left_norm = math.sqrt(sum(value * value for value in left_terms.values()))
    right_norm = math.sqrt(sum(value * value for value in right_terms.values()))
    return dot_product / (left_norm * right_norm)


def _vector_cosine(left: Sequence[float], right: Sequence[float]) -> float:
    """中文：对等长数值向量计算防零除余弦相似度。

    English: Compute zero-safe cosine similarity for equal-length numeric vectors.
    """

    if not left or len(left) != len(right):
        return 0.0
    dot_product = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot_product / (left_norm * right_norm)


def _extract_json(text: str) -> str:
    """中文：从可能带 Markdown 围栏的模型输出中提取首个 JSON 对象。

    English: Extract the first JSON object from a model response that may contain fences.
    """

    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("model response does not contain a JSON object")
    return text[start : end + 1]
