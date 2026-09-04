"""中文：定义外部索引制品与数据库原子发布之间的稳定契约。

English: Define stable contracts between external index artifacts and atomic DB publication.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class PublicationPlan:
    """中文：冻结构建候选索引所依据的活动状态和文档版本集合。

    English: Freeze expected active state and document versions for a candidate index build.
    """

    tenant_id: str
    new_index_version_id: str
    expected_active_index_version_id: str | None
    document_version_ids: tuple[str, ...]
    manifest_fingerprint: str


@dataclass(frozen=True, slots=True)
class StagedIndex:
    """中文：保存已经构建但尚未获得数据库发布权的不可变候选制品。

    English: Store an immutable candidate artifact built before database publication authority.
    """

    tenant_id: str
    index_version_id: str
    staging_path: Path
    manifest_fingerprint: str
    chunk_count: int


@dataclass(frozen=True, slots=True)
class PublicationCommit:
    """中文：保存原子发布事务需要验证的 fence 和 generation。

    English: Store fence and generation values validated by the atomic publication transaction.
    """

    tenant_id: str
    document_id: str | None
    document_version_id: str | None
    job_id: str | None
    worker_token: str | None
    lease_generation: int | None
    document_generation: int | None
    new_index_version_id: str
    expected_active_index_version_id: str | None
    manifest_fingerprint: str


@dataclass(frozen=True, slots=True)
class PublicationResult:
    """中文：描述成功激活的新索引和被安全退役的旧索引。

    English: Describe the activated index and safely retired prior index.
    """

    index_version_id: str
    previous_index_version_id: str | None
    activated: bool
    chunk_count: int
