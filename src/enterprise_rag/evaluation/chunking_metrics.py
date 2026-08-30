"""中文：计算自适应中文切块的结构完整性、可复现性与质量门指标。

English: Compute structural integrity, reproducibility, and quality-gate metrics for adaptive
Chinese chunking.
"""

from __future__ import annotations

from dataclasses import dataclass

from enterprise_rag.domain.models import Chunk

# 中文：这些结构角色必须保持独立，混入同一叶子块通常表示越过了硬边界。
# English: These protected roles must remain isolated; co-occurrence usually crosses a hard edge.
_PROTECTED_ROLES = frozenset({"warning", "table", "code", "api_section", "numbered_clause"})


@dataclass(frozen=True, slots=True)
class ChunkingMetrics:
    """中文：保存一次切块结果的稳定、可序列化验收指标。

    English: Hold stable, serializable acceptance metrics for one chunking result.
    """

    # 中文：硬边界疑似违反次数；发布目标必须为零。
    # English: Suspected hard-boundary violations; the publication target is zero.
    hard_boundary_violations: int
    # 中文：有标题路径的叶子块占比，用于验证检索结构保留。
    # English: Share of leaf chunks retaining heading paths for structured retrieval.
    heading_path_retention: float
    # 中文：相同内容哈希重复比例，过高会挤占 Top-K。
    # English: Duplicate content-hash ratio; high values crowd out Top-K.
    duplicate_content_ratio: float
    # 中文：Parent-Child 双向关系完整率。
    # English: Integrity ratio of bidirectional parent-child relations.
    parent_child_integrity: float
    # 中文：超过指定硬 Token 上限的叶子块数量。
    # English: Number of leaves exceeding the configured hard token ceiling.
    oversized_leaf_count: int
    # 中文：叶子边界置信度均值，供分画像调参与回归监控。
    # English: Mean leaf-boundary confidence for profile tuning and regression monitoring.
    mean_boundary_confidence: float

    def as_dict(self) -> dict[str, float | int]:
        """中文：返回适合 JSON 报告与发布门禁的稳定字段映射。

        English: Return a stable field mapping for JSON reports and release gates.
        """

        return {
            "hard_boundary_violations": self.hard_boundary_violations,
            "heading_path_retention": self.heading_path_retention,
            "duplicate_content_ratio": self.duplicate_content_ratio,
            "parent_child_integrity": self.parent_child_integrity,
            "oversized_leaf_count": self.oversized_leaf_count,
            "mean_boundary_confidence": self.mean_boundary_confidence,
        }


def evaluate_chunking(
    chunks: tuple[Chunk, ...],
    *,
    max_leaf_tokens: int,
) -> ChunkingMetrics:
    """中文：对完整 Chunk 集执行确定性质量度量，不调用模型或外部服务。

    English: Deterministically measure a complete chunk set without models or external services.
    """

    if max_leaf_tokens < 1:
        raise ValueError("max_leaf_tokens must be positive")
    leaves = tuple(chunk for chunk in chunks if chunk.chunk_level == "leaf")
    parents = {chunk.id: chunk for chunk in chunks if chunk.chunk_level == "parent"}
    if not leaves:
        return ChunkingMetrics(0, 1.0, 0.0, 1.0, 0, 1.0)

    # 中文：同一叶子块出现多个受保护角色表示边界隔离规则失效。
    # English: Multiple protected roles in one leaf indicate failed hard-boundary isolation.
    hard_boundary_violations = 0
    valid_parent_links = 0
    linked_leaves = 0
    for leaf in leaves:
        raw_roles = leaf.metadata.get("unit_types", [leaf.unit_type])
        roles = {str(role) for role in raw_roles} if isinstance(raw_roles, list) else set()
        if len(roles & _PROTECTED_ROLES) > 1:
            hard_boundary_violations += 1
        if leaf.parent_chunk_id is not None:
            linked_leaves += 1
            parent = parents.get(leaf.parent_chunk_id)
            child_ids = parent.metadata.get("child_chunk_ids", []) if parent else []
            if parent is not None and isinstance(child_ids, list) and leaf.id in child_ids:
                valid_parent_links += 1

    unique_hashes = len({chunk.content_hash for chunk in leaves})
    linked_integrity = valid_parent_links / linked_leaves if linked_leaves else 1.0
    return ChunkingMetrics(
        hard_boundary_violations=hard_boundary_violations,
        heading_path_retention=sum(bool(chunk.heading_path) for chunk in leaves) / len(leaves),
        duplicate_content_ratio=1.0 - unique_hashes / len(leaves),
        parent_child_integrity=linked_integrity,
        oversized_leaf_count=sum(chunk.token_count > max_leaf_tokens for chunk in leaves),
        mean_boundary_confidence=sum(chunk.boundary_confidence for chunk in leaves) / len(leaves),
    )


def deterministic_chunk_match(
    first: tuple[Chunk, ...],
    second: tuple[Chunk, ...],
) -> float:
    """中文：比较稳定 ID、顺序、哈希和父子映射，返回零到一的一致率。

    English: Compare stable IDs, order, hashes, and hierarchy and return a zero-to-one match.
    """

    if not first and not second:
        return 1.0
    maximum = max(len(first), len(second))
    if maximum == 0:
        return 1.0
    matches = sum(
        left.id == right.id
        and left.ordinal == right.ordinal
        and left.content_hash == right.content_hash
        and left.parent_chunk_id == right.parent_chunk_id
        for left, right in zip(first, second, strict=False)
    )
    return matches / maximum
