"""中文：本模块负责实现“向量索引”相关功能。

English: Build, save, reload, and permission-filter a normalized FAISS inner-product index.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from enterprise_rag.domain.models import RetrievalScope
from enterprise_rag.indexing.models import IndexBuildPlan, IndexEntry


class VectorIndexBuilder:
    """中文：该类用于表示或实现“向量索引构建器（VectorIndexBuilder）”的职责。

    English: Build a FAISS IndexFlatIP artifact with an explicit integer-to-chunk mapping.
    """

    def build(self, plan: IndexBuildPlan, vectors: np.ndarray, directory: Path) -> tuple[Path, ...]:
        """中文：该函数或方法负责“构建目标对象”相关处理。

        English: Write the vector component and aligned ACL metadata into a staging directory.
        """

        if vectors.ndim != 2 or vectors.shape[0] != len(plan.entries):
            raise ValueError("vector row count must match the build plan")
        # 中文：本步骤涉及提供方，具体约束见下方英文说明。
        # English: FAISS is loaded lazily so non-local-provider tooling can import the
        #   project.
        try:
            import faiss
        except ImportError as exc:
            raise RuntimeError(
                "faiss-cpu is required to build dense indexes; install the local-models extra"
            ) from exc
        directory.mkdir(parents=True, exist_ok=True)
        # 中文：变量 `index` 用于保存“索引”相关数据；其精确定义与约束见下方英文说明。
        # English: Exact inner-product index is correct because EmbeddingService
        #   normalizes vectors.
        index = faiss.IndexFlatIP(int(vectors.shape[1]))
        index.add(np.ascontiguousarray(vectors, dtype=np.float32))
        # 中文：变量 `index_path` 用于保存“索引`path`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Dense binary artifact contains only numeric vectors and implicit
        #   integer IDs.
        index_path = directory / "dense.faiss"
        faiss.write_index(index, str(index_path))
        # 中文：变量 `mapping_path` 用于保存“`mapping``path`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Explicit mapping makes FAISS row IDs stable and auditable.
        mapping_path = directory / "dense_mapping.json"
        mapping_path.write_text(
            json.dumps(
                {
                    "index_version_id": plan.index_version_id,
                    "dimension": int(vectors.shape[1]),
                    "entries": [asdict(entry) for entry in plan.entries],
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        return index_path, mapping_path


class FaissVectorIndex:
    """中文：该类用于表示或实现“FAISS向量索引（FaissVectorIndex）”的职责。

    English: Search one immutable FAISS artifact and apply exact scope filters before output.
    """

    def __init__(self, version_id: str, index: Any, entries: tuple[IndexEntry, ...]) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store a loaded FAISS index and its row-aligned metadata.
        """

        # 中文：变量 `_version_id` 用于保存“版本标识符”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Immutable snapshot identifier prevents cross-version composition.
        self._version_id = version_id
        # 中文：变量 `_index` 用于保存“索引”相关数据；其精确定义与约束见下方英文说明。
        # English: FAISS IndexFlatIP instance owns normalized vectors.
        self._index = index
        # 中文：变量 `_entries` 用于保存“`entries`”相关数据；其精确定义与约束见下方英文说明。
        # English: Entry tuple maps each returned integer row to stable domain identity.
        self._entries = entries

    @property
    def version_id(self) -> str:
        """中文：该函数或方法负责“版本标识符”相关处理。

        English: Return the immutable snapshot identifier.
        """

        return self._version_id

    @classmethod
    def load(cls, directory: Path) -> FaissVectorIndex:
        """中文：该函数或方法负责“加载并解析目标数据”相关处理。

        English: Reload a staged or published component and validate row alignment.
        """

        try:
            import faiss
        except ImportError as exc:
            raise RuntimeError("faiss-cpu is required to load dense indexes") from exc
        # 中文：变量 `payload` 用于保存“载荷”相关数据；其精确定义与约束见下方英文说明。
        # English: Mapping is parsed before accepting the binary artifact.
        payload = json.loads((directory / "dense_mapping.json").read_text(encoding="utf-8"))
        # 中文：变量 `entries` 用于保存“`entries`”相关数据；其精确定义与约束见下方英文说明。
        # English: Domain-aligned entries restore ACL metadata for pre-output filtering.
        entries = tuple(IndexEntry(**item) for item in payload["entries"])
        # 中文：变量 `index` 用于保存“索引”相关数据；其精确定义与约束见下方英文说明。
        # English: FAISS binary is reloaded to validate staging output before publication.
        index = faiss.read_index(str(directory / "dense.faiss"))
        if index.ntotal != len(entries) or index.d != int(payload["dimension"]):
            raise ValueError("dense index and mapping metadata are inconsistent")
        return cls(str(payload["index_version_id"]), index, entries)

    def search(
        self,
        query_vector: Sequence[float],
        limit: int,
        scope: RetrievalScope,
    ) -> tuple[tuple[str, float], ...]:
        """中文：该函数或方法负责“执行一次搜索”相关处理。

        English: Return highest-scoring authorized chunks without leaking filtered candidates.
        """

        if scope.index_version_id and scope.index_version_id != self._version_id:
            raise ValueError("retrieval scope and dense index versions differ")
        # 中文：空索引在生成查询矩阵前直接返回，避免占位维度与真实模型维度比较。
        # English: Empty indexes return before query construction so placeholder and model
        # dimensions never need to match.
        if not self._entries:
            return ()
        # 中文：变量 `raw_limit` 用于保存“`raw``limit`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Oversampling is required because IndexFlatIP cannot natively filter
        #   arbitrary ACLs.
        raw_limit = min(len(self._entries), max(limit * 4, limit))
        # 中文：变量 `query` 用于保存“查询”相关数据；其精确定义与约束见下方英文说明。
        # English: Query matrix must be contiguous float32 for FAISS.
        query = np.asarray(query_vector, dtype=np.float32).reshape(1, -1)
        # 中文：变量 `norm` 用于保存“`norm`”相关数据；其精确定义与约束见下方英文说明。
        # English: Query normalization protects callers that bypass EmbeddingService.
        norm = np.linalg.norm(query)
        if norm == 0:
            return ()
        normalized_query = np.ascontiguousarray(query / norm)
        authorized: list[tuple[str, float]] = []
        # 中文：逐步扩大 FAISS 搜索窗口，直到补足授权结果或扫描完整索引。
        # English: Expand the FAISS window until enough authorized hits are found or all rows
        # have been scanned.
        while True:
            scores, row_ids = self._index.search(normalized_query, raw_limit)
            authorized = []
            for score, row_id in zip(scores[0], row_ids[0], strict=True):
                if row_id < 0:
                    continue
                entry = self._entries[int(row_id)]
                if scope.allows(entry.tenant_id, entry.source_id, entry.document_id):
                    authorized.append((entry.chunk_id, float(score)))
                    if len(authorized) >= limit:
                        break
            if len(authorized) >= limit or raw_limit >= len(self._entries):
                break
            raw_limit = min(len(self._entries), raw_limit * 2)
        return tuple(authorized)
