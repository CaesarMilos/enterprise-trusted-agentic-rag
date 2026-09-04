"""中文：集中声明 V4 关键状态机，拒绝跨生命周期的非法跃迁。

English: Centralize V4 state machines and reject illegal cross-lifecycle transitions.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TypeVar

from enterprise_rag.core.enums import (
    DocumentLifecycleStatus,
    DocumentOperationalStatus,
    DocumentStatus,
    DocumentVersionStatus,
    IndexStatus,
    JobExecutionStatus,
    JobStatus,
    QualityDecision,
    SnapshotStatus,
    StateActor,
)

StateT = TypeVar("StateT", DocumentStatus, JobStatus, IndexStatus)

# 中文：删除态不可返回 READY；只有新 generation 才能重新创建处理链路。
# English: Deletion states never return to READY; only a new generation may start new work.
DOCUMENT_TRANSITIONS: Mapping[DocumentStatus, frozenset[DocumentStatus]] = {
    DocumentStatus.PENDING: frozenset({DocumentStatus.PROCESSING, DocumentStatus.PENDING_DELETE}),
    DocumentStatus.PROCESSING: frozenset(
        {
            DocumentStatus.READY,
            DocumentStatus.NEEDS_OCR,
            DocumentStatus.NEEDS_REVIEW,
            DocumentStatus.UNSUPPORTED,
            DocumentStatus.FAILED,
            DocumentStatus.PENDING_DELETE,
        }
    ),
    DocumentStatus.READY: frozenset({DocumentStatus.PROCESSING, DocumentStatus.PENDING_DELETE}),
    DocumentStatus.NEEDS_OCR: frozenset({DocumentStatus.PROCESSING, DocumentStatus.PENDING_DELETE}),
    DocumentStatus.NEEDS_REVIEW: frozenset(
        {DocumentStatus.PROCESSING, DocumentStatus.PENDING_DELETE}
    ),
    DocumentStatus.UNSUPPORTED: frozenset(
        {DocumentStatus.PROCESSING, DocumentStatus.PENDING_DELETE}
    ),
    DocumentStatus.FAILED: frozenset({DocumentStatus.PROCESSING, DocumentStatus.PENDING_DELETE}),
    DocumentStatus.PENDING_DELETE: frozenset({DocumentStatus.DELETED}),
    DocumentStatus.DELETED: frozenset(),
}

# 中文：任务终态不可复活；重试通过新的 attempt/fence 或新任务完成。
# English: Terminal jobs never revive; retries use a new attempt/fence or a new job.
JOB_TRANSITIONS: Mapping[JobStatus, frozenset[JobStatus]] = {
    JobStatus.PENDING: frozenset({JobStatus.RUNNING, JobStatus.CANCELLED}),
    JobStatus.RUNNING: frozenset(
        {
            JobStatus.SUCCEEDED,
            JobStatus.NEEDS_OCR,
            JobStatus.NEEDS_REVIEW,
            JobStatus.UNSUPPORTED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        }
    ),
    **{
        status: frozenset()
        for status in JobStatus
        if status not in {JobStatus.PENDING, JobStatus.RUNNING}
    },
}

# 中文：候选索引只有经过验证才能激活；失败和取消制品只能回收。
# English: A candidate activates only after validation; failed/cancelled artifacts may only purge.
INDEX_TRANSITIONS: Mapping[IndexStatus, frozenset[IndexStatus]] = {
    IndexStatus.STAGING: frozenset({IndexStatus.READY, IndexStatus.FAILED, IndexStatus.CANCELLED}),
    IndexStatus.READY: frozenset({IndexStatus.ACTIVE, IndexStatus.FAILED, IndexStatus.CANCELLED}),
    IndexStatus.ACTIVE: frozenset({IndexStatus.RETIRED}),
    IndexStatus.RETIRED: frozenset({IndexStatus.PURGED}),
    IndexStatus.FAILED: frozenset({IndexStatus.PURGED}),
    IndexStatus.CANCELLED: frozenset({IndexStatus.PURGED}),
    IndexStatus.PURGED: frozenset(),
}


def ensure_transition(
    current: StateT,
    target: StateT,
    transitions: Mapping[StateT, frozenset[StateT]],
) -> None:
    """中文：验证显式状态跃迁；同状态写入作为幂等操作被允许。

    English: Validate an explicit transition while allowing idempotent writes to the same state.
    """

    if current != target and target not in transitions.get(current, frozenset()):
        raise ValueError(f"illegal state transition: {current!s} -> {target!s}")


@dataclass(frozen=True, slots=True)
class TransitionRule:
    """中文：描述一条目标状态及获准执行该跃迁的组件。

    English: Describe a target state and components authorized to perform the transition.
    """

    target: object
    allowed_actors: frozenset[StateActor]


# 中文：V5 文档生命周期只表达逻辑存在和不可逆删除。
# English: V5 document lifecycle describes logical existence and irreversible deletion only.
DOCUMENT_LIFECYCLE_RULES: Mapping[DocumentLifecycleStatus, tuple[TransitionRule, ...]] = {
    DocumentLifecycleStatus.ACTIVE: (
        TransitionRule(
            DocumentLifecycleStatus.PENDING_DELETE,
            frozenset({StateActor.DELETION_SERVICE}),
        ),
    ),
    DocumentLifecycleStatus.PENDING_DELETE: (
        TransitionRule(
            DocumentLifecycleStatus.DELETED,
            frozenset({StateActor.DELETION_WORKER}),
        ),
    ),
    DocumentLifecycleStatus.DELETED: (),
}

# 中文：候选版本只有发布服务可以激活，Worker 只能拒绝无效产物。
# English: Only publication activates candidates; workers may only reject invalid artifacts.
DOCUMENT_VERSION_RULES: Mapping[DocumentVersionStatus, tuple[TransitionRule, ...]] = {
    DocumentVersionStatus.CANDIDATE: (
        TransitionRule(
            DocumentVersionStatus.PUBLISHED,
            frozenset({StateActor.PUBLICATION_SERVICE}),
        ),
        TransitionRule(
            DocumentVersionStatus.REJECTED,
            frozenset({StateActor.INGESTION_WORKER, StateActor.MIGRATION}),
        ),
    ),
    DocumentVersionStatus.PUBLISHED: (
        TransitionRule(
            DocumentVersionStatus.SUPERSEDED,
            frozenset({StateActor.PUBLICATION_SERVICE}),
        ),
    ),
    DocumentVersionStatus.REJECTED: (),
    DocumentVersionStatus.SUPERSEDED: (),
}

# 中文：任务恢复只能由恢复服务完成，普通重试通过创建新任务实现。
# English: Only recovery may requeue jobs; normal retries create a new durable job.
JOB_EXECUTION_RULES: Mapping[JobExecutionStatus, tuple[TransitionRule, ...]] = {
    JobExecutionStatus.QUEUED: (
        TransitionRule(
            JobExecutionStatus.RUNNING,
            frozenset({StateActor.INGESTION_WORKER, StateActor.DELETION_WORKER}),
        ),
        TransitionRule(
            JobExecutionStatus.CANCELLED,
            frozenset({StateActor.INGESTION_SERVICE, StateActor.DELETION_SERVICE}),
        ),
        TransitionRule(JobExecutionStatus.STALE, frozenset({StateActor.RECOVERY_SERVICE})),
        TransitionRule(
            JobExecutionStatus.DEAD_LETTER,
            frozenset({StateActor.RECOVERY_SERVICE}),
        ),
    ),
    JobExecutionStatus.RUNNING: (
        TransitionRule(
            JobExecutionStatus.SUCCEEDED,
            frozenset({StateActor.INGESTION_WORKER, StateActor.DELETION_WORKER}),
        ),
        TransitionRule(
            JobExecutionStatus.FAILED,
            frozenset({StateActor.INGESTION_WORKER, StateActor.DELETION_WORKER}),
        ),
        TransitionRule(
            JobExecutionStatus.CANCELLED,
            frozenset({StateActor.INGESTION_WORKER, StateActor.DELETION_WORKER}),
        ),
        TransitionRule(
            JobExecutionStatus.STALE,
            frozenset({StateActor.INGESTION_WORKER, StateActor.RECOVERY_SERVICE}),
        ),
        TransitionRule(JobExecutionStatus.QUEUED, frozenset({StateActor.RECOVERY_SERVICE})),
        TransitionRule(
            JobExecutionStatus.DEAD_LETTER,
            frozenset({StateActor.RECOVERY_SERVICE}),
        ),
    ),
    **{
        status: ()
        for status in JobExecutionStatus
        if status not in {JobExecutionStatus.QUEUED, JobExecutionStatus.RUNNING}
    },
}

SNAPSHOT_RULES: Mapping[SnapshotStatus, tuple[TransitionRule, ...]] = {
    SnapshotStatus.ACTIVE: (
        TransitionRule(SnapshotStatus.CLOSED, frozenset({StateActor.SNAPSHOT_SERVICE})),
        TransitionRule(SnapshotStatus.EXPIRED, frozenset({StateActor.SNAPSHOT_SERVICE})),
        TransitionRule(SnapshotStatus.REVOKED, frozenset({StateActor.SNAPSHOT_SERVICE})),
    ),
    SnapshotStatus.CLOSED: (),
    SnapshotStatus.EXPIRED: (),
    SnapshotStatus.REVOKED: (),
}


def ensure_transition_authorized(
    current: object,
    target: object,
    actor: StateActor,
    rules: Mapping[object, tuple[TransitionRule, ...]],
) -> None:
    """中文：同时验证 V5 状态边和执行组件的修改权限。

    English: Validate both a V5 transition edge and the mutating component's authority.
    """

    if current == target:
        return
    matching = next((rule for rule in rules.get(current, ()) if rule.target == target), None)
    if matching is None:
        raise ValueError(f"illegal state transition: {current!s} -> {target!s}")
    if actor not in matching.allowed_actors:
        raise PermissionError(
            f"state actor {actor!s} cannot perform transition {current!s} -> {target!s}"
        )


def derive_document_operational_status(
    lifecycle: DocumentLifecycleStatus,
    active_version_status: DocumentVersionStatus | None,
    active_quality: QualityDecision | None,
    latest_job_status: JobExecutionStatus | None,
) -> DocumentOperationalStatus:
    """中文：从独立状态机派生面向 API/UI 的文档状态。

    English: Derive an API/UI document status from independent state machines.
    """

    if lifecycle is DocumentLifecycleStatus.DELETED:
        return DocumentOperationalStatus.DELETED
    if lifecycle is DocumentLifecycleStatus.PENDING_DELETE:
        return DocumentOperationalStatus.PENDING_DELETE
    if active_version_status is DocumentVersionStatus.PUBLISHED:
        if active_quality is QualityDecision.PASS_WITH_WARNINGS:
            return DocumentOperationalStatus.READY_WITH_WARNINGS
        return DocumentOperationalStatus.READY
    if latest_job_status is JobExecutionStatus.RUNNING:
        return DocumentOperationalStatus.PROCESSING
    if latest_job_status is JobExecutionStatus.QUEUED:
        return DocumentOperationalStatus.PENDING
    if active_quality is QualityDecision.NEEDS_REVIEW:
        return DocumentOperationalStatus.NEEDS_REVIEW
    if latest_job_status in {JobExecutionStatus.FAILED, JobExecutionStatus.DEAD_LETTER}:
        return DocumentOperationalStatus.FAILED
    return DocumentOperationalStatus.PENDING


def is_version_servable(
    lifecycle: DocumentLifecycleStatus,
    version_status: DocumentVersionStatus,
    quality: QualityDecision,
    currently_revoked: bool,
) -> bool:
    """中文：判断版本是否同时满足生命周期、发布、质量和撤销门禁。

    English: Check lifecycle, publication, quality, and revocation gates for serving a version.
    """

    return (
        lifecycle is DocumentLifecycleStatus.ACTIVE
        and version_status is DocumentVersionStatus.PUBLISHED
        and quality in {QualityDecision.PASS, QualityDecision.PASS_WITH_WARNINGS}
        and not currently_revoked
    )
