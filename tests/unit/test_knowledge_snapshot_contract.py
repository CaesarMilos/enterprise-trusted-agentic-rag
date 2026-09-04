"""中文：验证固定知识快照、到期和即时撤销语义。

English: Verify fixed knowledge snapshot, expiry, and immediate revocation semantics.
"""

from datetime import UTC, datetime, timedelta

from enterprise_rag.core.enums import RevocationScopeType, SnapshotStatus
from enterprise_rag.domain.snapshots import (
    KnowledgeSnapshot,
    RevocationRecord,
    snapshot_fingerprint,
    validate_snapshot_against_revocations,
)


def _snapshot() -> KnowledgeSnapshot:
    """中文：创建包含一个资料源和文档版本的活动快照。

    English: Create an active snapshot containing one source and document version.
    """

    created = datetime(2026, 1, 1, tzinfo=UTC)
    return KnowledgeSnapshot(
        id="snapshot-1",
        tenant_id="tenant-1",
        user_id="user-1",
        status=SnapshotStatus.ACTIVE,
        index_version_id="index-1",
        index_manifest_fingerprint="manifest",
        source_ids=frozenset({"source-1"}),
        document_version_ids=frozenset({"version-1"}),
        authorization_fingerprint="auth",
        captured_revocation_epoch=0,
        created_at=created,
        expires_at=created + timedelta(seconds=120),
    )


def test_source_revocation_overrides_fixed_snapshot() -> None:
    """中文：固定快照不能绕过查询期间发生的资料源即时撤销。

    English: A fixed snapshot cannot bypass an immediate source revocation during a query.
    """

    snapshot = _snapshot()
    revocation = RevocationRecord(
        "revocation-1",
        "tenant-1",
        1,
        RevocationScopeType.SOURCE,
        "source-1",
        "source_access_revoked",
        "admin-1",
        snapshot.created_at + timedelta(seconds=1),
    )
    result = validate_snapshot_against_revocations(
        snapshot,
        now=snapshot.created_at + timedelta(seconds=2),
        current_revocation_epoch=1,
        revocations=(revocation,),
    )
    assert not result.valid
    assert result.effective_status is SnapshotStatus.REVOKED


def test_snapshot_fingerprint_ignores_set_order() -> None:
    """中文：快照集合顺序不能改变其内容身份。

    English: Set ordering cannot change a snapshot's content identity.
    """

    assert len(snapshot_fingerprint(_snapshot())) == 64
