"""中文：集中声明 V4 关键状态机，拒绝跨生命周期的非法跃迁。

English: Centralize V4 state machines and reject illegal cross-lifecycle transitions.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypeVar

from enterprise_rag.core.enums import DocumentStatus, IndexStatus, JobStatus

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
    IndexStatus.STAGING: frozenset(
        {IndexStatus.READY, IndexStatus.FAILED, IndexStatus.CANCELLED}
    ),
    IndexStatus.READY: frozenset(
        {IndexStatus.ACTIVE, IndexStatus.FAILED, IndexStatus.CANCELLED}
    ),
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
