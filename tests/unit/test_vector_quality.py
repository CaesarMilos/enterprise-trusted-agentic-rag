"""中文：验证向量质量门阻止不同正文产生完全相同向量。

English: Verify the vector quality gate blocks exact vectors across distinct bodies.
"""

from __future__ import annotations

import numpy as np
import pytest

from enterprise_rag.indexing.models import IndexEntry
from enterprise_rag.indexing.vector_quality import VectorQualityValidator


def _entry(ordinal: int, fingerprint: str) -> IndexEntry:
    """中文：构造具有独立正文指纹的索引条目。

    English: Build one index entry with an independent body fingerprint.
    """

    return IndexEntry(
        chunk_id=f"chunk-{ordinal}",
        tenant_id="tenant-a",
        source_id="source-a",
        document_id="document-a",
        document_version_id="version-a",
        text=f"body-{ordinal}",
        content_fingerprint=fingerprint,
    )


def test_distinct_bodies_with_same_vectors_block_publication() -> None:
    """中文：四份不同正文共享同一向量时必须报告表示塌缩。

    English: Report representation collapse when four distinct bodies share one vector.
    """

    entries = tuple(_entry(index, f"hash-{index}") for index in range(4))
    vectors = np.tile(np.asarray([[1.0, 0.0]], dtype=np.float32), (4, 1))

    with pytest.raises(ValueError, match="DENSE_VECTOR_COLLAPSE"):
        VectorQualityValidator(max_exact_duplicate_group=3).validate(vectors, entries)


def test_true_duplicate_content_is_reported_without_false_collapse() -> None:
    """中文：同一正文的合法重复不应被误判为不同内容的表示塌缩。

    English: Do not mistake legitimate duplicate bodies for cross-content collapse.
    """

    entries = tuple(_entry(index, "same-body") for index in range(2))
    vectors = np.tile(np.asarray([[1.0, 0.0]], dtype=np.float32), (2, 1))

    report = VectorQualityValidator(max_exact_duplicate_group=3).validate(vectors, entries)

    assert report.passed is True
    assert report.harmful_duplicate_vectors == 0
