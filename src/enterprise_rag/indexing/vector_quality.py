"""中文：本模块在索引发布前检测精确向量重复与表示塌缩。

English: Detect exact duplicate vectors and representation collapse before index publication.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

from enterprise_rag.indexing.models import IndexEntry


@dataclass(frozen=True, slots=True)
class VectorQualityReport:
    """中文：保存向量碰撞检测的可审计统计结果。

    English: Store auditable statistics from vector-collision validation.
    """

    total_vectors: int
    unique_vectors: int
    largest_exact_duplicate_group: int
    largest_harmful_duplicate_group: int
    harmful_duplicate_vectors: int
    harmful_duplicate_ratio: float
    passed: bool


class VectorQualityValidator:
    """中文：阻止不同正文因截断或模型异常生成大规模完全相同向量。

    English: Block large exact-vector groups across distinct bodies caused by truncation or
    provider failure.
    """

    def __init__(
        self,
        max_exact_duplicate_group: int = 3,
        max_harmful_duplicate_ratio: float = 0.01,
    ) -> None:
        """中文：保存向量组大小和有害碰撞比例的发布门槛。

        English: Store publication thresholds for duplicate groups and harmful ratio.
        """

        if max_exact_duplicate_group < 1:
            raise ValueError("maximum duplicate vector group must be positive")
        if not 0.0 <= max_harmful_duplicate_ratio <= 1.0:
            raise ValueError("harmful duplicate ratio must be between zero and one")
        self._max_group = max_exact_duplicate_group
        self._max_ratio = max_harmful_duplicate_ratio

    def validate(
        self,
        vectors: npt.NDArray[np.float32],
        entries: tuple[IndexEntry, ...],
    ) -> VectorQualityReport:
        """中文：按 float32 原始字节分组，并区分正文真重复与表示塌缩。

        English: Group float32 bytes and distinguish true body duplicates from collapse.
        """

        if vectors.ndim != 2 or vectors.shape[0] != len(entries):
            raise ValueError("vector quality input must align with index entries")
        # 中文：关键变量 `groups` 将精确向量哈希映射到行号，结果不受浮点排序影响。
        # English: Key variable `groups` maps exact-vector hashes to rows without score ordering.
        groups: dict[str, list[int]] = {}
        for row_id, vector in enumerate(vectors):
            vector_bytes = np.ascontiguousarray(vector, dtype=np.float32).tobytes()
            groups.setdefault(hashlib.sha256(vector_bytes).hexdigest(), []).append(row_id)
        harmful_rows: set[int] = set()
        largest_group = 0
        largest_harmful_group = 0
        for row_ids in groups.values():
            largest_group = max(largest_group, len(row_ids))
            body_fingerprints = {
                entries[row_id].content_fingerprint or entries[row_id].text
                for row_id in row_ids
            }
            if len(row_ids) > 1 and len(body_fingerprints) > 1:
                harmful_rows.update(row_ids)
                largest_harmful_group = max(largest_harmful_group, len(row_ids))
        total = len(entries)
        harmful_ratio = len(harmful_rows) / total if total else 0.0
        passed = largest_harmful_group <= self._max_group and harmful_ratio <= self._max_ratio
        report = VectorQualityReport(
            total_vectors=total,
            unique_vectors=len(groups),
            largest_exact_duplicate_group=largest_group,
            largest_harmful_duplicate_group=largest_harmful_group,
            harmful_duplicate_vectors=len(harmful_rows),
            harmful_duplicate_ratio=round(harmful_ratio, 6),
            passed=passed,
        )
        if not report.passed:
            raise ValueError(
                "DENSE_VECTOR_COLLAPSE: distinct index entries share unsafe exact vectors "
                f"(largest_group={largest_harmful_group}, harmful_ratio={harmful_ratio:.6f})"
            )
        return report


def save_vector_quality_report(report: VectorQualityReport, directory: Path) -> Path:
    """中文：把向量质量报告写入不可变索引制品目录。

    English: Persist the vector quality report inside the immutable index artifact directory.
    """

    report_path = directory / "vector_quality.json"
    report_path.write_text(
        json.dumps(asdict(report), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return report_path
