"""中文：本模块负责实现“BM25 关键词检索索引”相关功能。

English: Build and query a deterministic bilingual BM25 index with embedded ACL metadata.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from enterprise_rag.domain.models import RetrievalScope
from enterprise_rag.indexing.models import IndexBuildPlan, IndexEntry
from enterprise_rag.retrieval.identifier_normalizer import extract_exact_anchors

# 中文：变量 `_TOKEN_PATTERN` 用于保存“词元`pattern`”相关数据；
# 其精确定义与约束见下方英文说明。
# English: Tokenizer retains Chinese characters and lowercased Latin word-like terms.
_CJK_SEQUENCE = re.compile(r"[\u3400-\u9fff]+")
_LATIN_TOKEN = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")
# 中文：高频疑问和连接词不应抬高来源路由或证据覆盖率。
# English: Frequent question and connective terms should not inflate routing or coverage.
_STOP_TERMS = frozenset(
    {"什么", "哪些", "如何", "怎么", "是否", "根据", "以及", "其中", "一个", "这个"}
)


def lexical_tokens(text: str) -> tuple[str, ...]:
    """中文：该函数或方法负责“关键词检索词元”相关处理。

    English: Tokenize Chinese and Latin text deterministically for indexing and queries.
    """

    normalized = unicodedata.normalize("NFKC", text).lower()
    tokens: list[str] = list(extract_exact_anchors(normalized))
    for sequence in _CJK_SEQUENCE.findall(normalized):
        if len(sequence) == 1:
            tokens.append(sequence)
            continue
        # 中文：二元词组保留中文局部语义；短词整体Token支持精确短语匹配。
        # English: Bigrams preserve local CJK meaning; short whole terms support phrase matching.
        tokens.extend(sequence[index : index + 2] for index in range(len(sequence) - 1))
        if len(sequence) <= 8:
            tokens.append(sequence)
    tokens.extend(_LATIN_TOKEN.findall(normalized))
    return tuple(token for token in tokens if token and token not in _STOP_TERMS)


class BM25IndexBuilder:
    """中文：该类用于表示或实现“BM25 关键词检索索引构建器（BM25IndexBuilder）”的职责。

    English: Serialize token frequencies and aligned entry metadata from one build plan.
    """

    def build(self, plan: IndexBuildPlan, directory: Path) -> tuple[Path, ...]:
        """中文：该函数或方法负责“构建目标对象”相关处理。

        English: Write one self-contained lexical artifact into a staging directory.
        """

        directory.mkdir(parents=True, exist_ok=True)
        # 中文：变量 `term_frequencies` 用于保存“`term``frequencies`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Per-document term counts preserve enough information for exact BM25
        #   scoring.
        term_frequencies = [dict(Counter(lexical_tokens(entry.text))) for entry in plan.entries]
        # 中文：变量 `document_lengths` 用于保存“文档`lengths`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Document lengths use the same tokenizer as term frequencies.
        document_lengths = [sum(frequencies.values()) for frequencies in term_frequencies]
        # 中文：变量 `artifact` 用于保存“制品”相关数据；其精确定义与约束见下方英文说明。
        # English: Artifact includes version and ACL metadata for independent reload
        #   validation.
        artifact = {
            "index_version_id": plan.index_version_id,
            "entries": [asdict(entry) for entry in plan.entries],
            "term_frequencies": term_frequencies,
            "document_lengths": document_lengths,
            "average_document_length": (
                sum(document_lengths) / len(document_lengths) if document_lengths else 0.0
            ),
        }
        artifact_path = directory / "bm25.json"
        artifact_path.write_text(
            json.dumps(artifact, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        return (artifact_path,)


class PersistentBM25Index:
    """中文：该类用于表示或实现“持久化BM25 关键词检索索引（PersistentBM25Index）”的职责。

    English: Score a reloaded immutable lexical corpus and filter it by exact retrieval scope.
    """

    def __init__(
        self,
        version_id: str,
        entries: tuple[IndexEntry, ...],
        term_frequencies: tuple[dict[str, int], ...],
        document_lengths: tuple[int, ...],
        average_document_length: float,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store a complete immutable corpus and conventional BM25 parameters.
        """

        # 中文：变量 `_version_id` 用于保存“版本标识符”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Snapshot identifier prevents cross-version fusion.
        self._version_id = version_id
        # 中文：变量 `_entries` 用于保存“`entries`”相关数据；其精确定义与约束见下方英文说明。
        # English: Row-aligned ACL and chunk identity metadata.
        self._entries = entries
        # 中文：变量 `_term_frequencies` 用于保存“`term``frequencies`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Row-aligned term-frequency mappings.
        self._term_frequencies = term_frequencies
        # 中文：变量 `_document_lengths` 用于保存“文档`lengths`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Row-aligned token counts.
        self._document_lengths = document_lengths
        # 中文：变量 `_average_document_length` 用于保存“`average`文档`length`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Corpus average used for length normalization.
        self._average_document_length = average_document_length
        # 中文：变量 `_k1` 用于保存“`k1`”相关数据；其精确定义与约束见下方英文说明。
        # English: Term-frequency saturation parameter.
        self._k1 = k1
        # 中文：变量 `_b` 用于保存“`b`”相关数据；其精确定义与约束见下方英文说明。
        # English: Document-length normalization parameter.
        self._b = b
        # 中文：变量 `_document_frequency` 用于保存“文档`frequency`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Document frequency is reconstructed once on load.
        self._document_frequency = Counter(
            term for frequencies in term_frequencies for term in frequencies
        )

    @property
    def version_id(self) -> str:
        """中文：该函数或方法负责“版本标识符”相关处理。

        English: Return the immutable snapshot identifier.
        """

        return self._version_id

    @classmethod
    def load(cls, directory: Path) -> PersistentBM25Index:
        """中文：该函数或方法负责“加载并解析目标数据”相关处理。

        English: Reload and validate the self-contained lexical artifact.
        """

        # 中文：变量 `payload` 用于保存“载荷”相关数据；其精确定义与约束见下方英文说明。
        # English: JSON artifact is immutable after index publication.
        payload = json.loads((directory / "bm25.json").read_text(encoding="utf-8"))
        # 中文：变量 `entries` 用于保存“`entries`”相关数据；其精确定义与约束见下方英文说明。
        # English: Entry tuple maps scores to stable chunks and ACL metadata.
        entries = tuple(IndexEntry(**item) for item in payload["entries"])
        # 中文：变量 `frequencies` 用于保存“`frequencies`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: JSON integer values are normalized explicitly for type stability.
        frequencies = tuple(
            {term: int(count) for term, count in item.items()}
            for item in payload["term_frequencies"]
        )
        # 中文：变量 `lengths` 用于保存“`lengths`”相关数据；其精确定义与约束见下方英文说明。
        # English: Document lengths remain row-aligned with entries.
        lengths = tuple(int(value) for value in payload["document_lengths"])
        if not len(entries) == len(frequencies) == len(lengths):
            raise ValueError("BM25 artifact arrays are inconsistent")
        return cls(
            version_id=str(payload["index_version_id"]),
            entries=entries,
            term_frequencies=frequencies,
            document_lengths=lengths,
            average_document_length=float(payload["average_document_length"]),
        )

    def search(
        self,
        query: str,
        limit: int,
        scope: RetrievalScope,
    ) -> tuple[tuple[str, float], ...]:
        """中文：该函数或方法负责“执行一次搜索”相关处理。

        English: Return highest-scoring authorized chunks for unique query terms.
        """

        if scope.index_version_id and scope.index_version_id != self._version_id:
            raise ValueError("retrieval scope and BM25 index versions differ")
        # 中文：变量 `query_terms` 用于保存“查询`terms`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Unique terms prevent repeated query words from arbitrarily scaling
        #   scores.
        query_terms = frozenset(lexical_tokens(query))
        # 中文：变量 `document_count` 用于保存“文档`count`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Corpus size is used by Robertson-Sparck Jones inverse document frequency.
        document_count = len(self._entries)
        # 中文：变量 `scored` 用于保存“`scored`”相关数据；其精确定义与约束见下方英文说明。
        # English: Scored collection contains authorized positive-score candidates only.
        scored: list[tuple[str, float]] = []
        for row_id, entry in enumerate(self._entries):
            if not scope.allows(entry.tenant_id, entry.source_id, entry.document_id):
                continue
            # 中文：变量 `score` 用于保存“计算相关性分数”相关数据；
            # 其精确定义与约束见下方英文说明。
            # English: Row score sums each query term's BM25 contribution.
            score = 0.0
            for term in query_terms:
                term_frequency = self._term_frequencies[row_id].get(term, 0)
                if term_frequency == 0:
                    continue
                document_frequency = self._document_frequency[term]
                inverse_document_frequency = math.log(
                    1 + (document_count - document_frequency + 0.5) / (document_frequency + 0.5)
                )
                # 中文：变量 `length_ratio` 用于保存“`length``ratio`”相关数据；
                # 其精确定义与约束见下方英文说明。
                # English: Zero average length occurs only for an empty-token corpus.
                length_ratio = (
                    self._document_lengths[row_id] / self._average_document_length
                    if self._average_document_length
                    else 0.0
                )
                denominator = term_frequency + self._k1 * (1 - self._b + self._b * length_ratio)
                score += inverse_document_frequency * (
                    term_frequency * (self._k1 + 1) / denominator
                )
            if score > 0:
                scored.append((entry.chunk_id, score))
        # 中文：本步骤涉及文本块、标识符，具体约束见下方英文说明。
        # English: Stable chunk ID breaks equal-score ties reproducibly.
        scored.sort(key=lambda item: (-item[1], item[0]))
        return tuple(scored[:limit])
