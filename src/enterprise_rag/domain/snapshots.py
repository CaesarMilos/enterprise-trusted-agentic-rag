"""中文：定义固定知识快照、即时撤销记录及其有效性结果。

English: Define fixed knowledge snapshots, immediate revocations, and validation results.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from enterprise_rag.core.enums import RevocationScopeType, SnapshotStatus
from enterprise_rag.core.ids import content_sha256


@dataclass(frozen=True, slots=True)
class KnowledgeSnapshot:
    """中文：冻结一次问答允许使用的索引、资料源和文档版本集合。

    English: Freeze the index, sources, and document versions allowed for one query.
    """

    id: str
    tenant_id: str
    user_id: str
    status: SnapshotStatus
    index_version_id: str
    index_manifest_fingerprint: str
    source_ids: frozenset[str]
    document_version_ids: frozenset[str]
    authorization_fingerprint: str
    captured_revocation_epoch: int
    created_at: datetime
    expires_at: datetime
    closed_at: datetime | None = None

    def __post_init__(self) -> None:
        """中文：校验快照范围、时间、撤销 epoch 和关闭状态的一致性。

        English: Validate snapshot scope, time, revocation epoch, and closure consistency.
        """

        identities = (
            self.id,
            self.tenant_id,
            self.user_id,
            self.index_version_id,
            self.index_manifest_fingerprint,
            self.authorization_fingerprint,
        )
        if any(not value for value in identities):
            raise ValueError("knowledge snapshot requires all identity fingerprints")
        if not self.source_ids or not self.document_version_ids:
            raise ValueError("knowledge snapshot requires source and version scopes")
        if self.expires_at <= self.created_at:
            raise ValueError("knowledge snapshot must expire after creation")
        if self.captured_revocation_epoch < 0:
            raise ValueError("captured revocation epoch cannot be negative")
        if self.status is SnapshotStatus.ACTIVE and self.closed_at is not None:
            raise ValueError("active knowledge snapshot cannot have a closed timestamp")
        if self.status is SnapshotStatus.CLOSED and self.closed_at is None:
            raise ValueError("closed knowledge snapshot requires a closed timestamp")

    def static_allows(
        self,
        *,
        tenant_id: str,
        source_id: str,
        document_version_id: str,
        index_version_id: str,
    ) -> bool:
        """中文：仅验证候选是否属于快照固定范围，不判断当前撤销。

        English: Validate fixed snapshot membership without checking current revocation state.
        """

        return (
            self.status is SnapshotStatus.ACTIVE
            and tenant_id == self.tenant_id
            and source_id in self.source_ids
            and document_version_id in self.document_version_ids
            and index_version_id == self.index_version_id
        )

    def is_expired(self, now: datetime) -> bool:
        """中文：按左闭边界判断快照租约是否到期。

        English: Return whether the snapshot lease expired using an inclusive boundary.
        """

        if now.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("snapshot expiry comparison requires timezone-aware timestamps")
        return now >= self.expires_at


@dataclass(frozen=True, slots=True)
class RevocationRecord:
    """中文：保存租户内严格递增的知识撤销事件。

    English: Store a strictly increasing tenant-scoped knowledge revocation event.
    """

    id: str
    tenant_id: str
    epoch: int
    scope_type: RevocationScopeType
    scope_id: str
    reason_code: str
    requested_by: str
    created_at: datetime

    def __post_init__(self) -> None:
        """中文：校验撤销对象、原因和正整数 epoch。

        English: Validate the revoked object, reason, and positive epoch.
        """

        if not all((self.id, self.tenant_id, self.scope_id, self.reason_code, self.requested_by)):
            raise ValueError("revocation record requires identities, scope, reason, and actor")
        if self.epoch < 1:
            raise ValueError("revocation epoch must be positive")


@dataclass(frozen=True, slots=True)
class SnapshotValidationResult:
    """中文：返回快照当前有效性及命中的撤销对象。

    English: Return current snapshot validity and matching revoked objects.
    """

    valid: bool
    effective_status: SnapshotStatus
    revoked_scope_ids: tuple[str, ...] = ()
    reason_code: str | None = None


def snapshot_fingerprint(snapshot: KnowledgeSnapshot) -> str:
    """中文：计算不受集合顺序和关闭状态影响的快照内容指纹。

    English: Compute a snapshot-content fingerprint independent of set order and closure state.
    """

    payload = {
        "authorization_fingerprint": snapshot.authorization_fingerprint,
        "captured_revocation_epoch": snapshot.captured_revocation_epoch,
        "document_version_ids": sorted(snapshot.document_version_ids),
        "expires_at": snapshot.expires_at.isoformat(),
        "index_manifest_fingerprint": snapshot.index_manifest_fingerprint,
        "index_version_id": snapshot.index_version_id,
        "source_ids": sorted(snapshot.source_ids),
        "tenant_id": snapshot.tenant_id,
    }
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return content_sha256(canonical)


def validate_snapshot_against_revocations(
    snapshot: KnowledgeSnapshot,
    *,
    now: datetime,
    current_revocation_epoch: int,
    revocations: tuple[RevocationRecord, ...] = (),
    version_to_document: dict[str, str] | None = None,
) -> SnapshotValidationResult:
    """中文：以关闭、过期和增量撤销的固定优先级验证快照。

    English: Validate a snapshot using fixed precedence for closure, expiry, and revocations.
    """

    if snapshot.status is SnapshotStatus.CLOSED:
        return SnapshotValidationResult(False, SnapshotStatus.CLOSED, reason_code="snapshot_closed")
    if snapshot.is_expired(now):
        return SnapshotValidationResult(
            False,
            SnapshotStatus.EXPIRED,
            reason_code="snapshot_expired",
        )
    if current_revocation_epoch < snapshot.captured_revocation_epoch:
        raise ValueError("current revocation epoch cannot precede the captured epoch")
    if current_revocation_epoch == snapshot.captured_revocation_epoch:
        return SnapshotValidationResult(True, SnapshotStatus.ACTIVE)
    documents = version_to_document or {}
    revoked_ids: list[str] = []
    for record in revocations:
        if (
            record.tenant_id != snapshot.tenant_id
            or record.epoch <= snapshot.captured_revocation_epoch
        ):
            continue
        if record.scope_type is RevocationScopeType.SOURCE:
            matched = record.scope_id in snapshot.source_ids
        elif record.scope_type is RevocationScopeType.DOCUMENT_VERSION:
            matched = record.scope_id in snapshot.document_version_ids
        else:
            matched = record.scope_id in {
                documents.get(version_id) for version_id in snapshot.document_version_ids
            }
        if matched:
            revoked_ids.append(record.scope_id)
    if revoked_ids:
        return SnapshotValidationResult(
            False,
            SnapshotStatus.REVOKED,
            tuple(dict.fromkeys(revoked_ids)),
            "snapshot_scope_revoked",
        )
    return SnapshotValidationResult(True, SnapshotStatus.ACTIVE)
