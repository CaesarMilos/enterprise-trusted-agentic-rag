"""中文：验证 V5 独立状态机和文档可服务派生规则。

English: Verify V5 independent state machines and document servability derivation.
"""

import pytest

from enterprise_rag.core.enums import (
    DocumentLifecycleStatus,
    DocumentOperationalStatus,
    DocumentVersionStatus,
    JobExecutionStatus,
    QualityDecision,
    StateActor,
)
from enterprise_rag.core.state_machine import (
    DOCUMENT_LIFECYCLE_RULES,
    derive_document_operational_status,
    ensure_transition_authorized,
    is_version_servable,
)


def test_document_delete_transition_is_irreversible_and_owned() -> None:
    """中文：删除服务可请求删除，但无权把文档恢复为活动状态。

    English: The deletion service may request deletion but cannot reactivate a document.
    """

    ensure_transition_authorized(
        DocumentLifecycleStatus.ACTIVE,
        DocumentLifecycleStatus.PENDING_DELETE,
        StateActor.DELETION_SERVICE,
        DOCUMENT_LIFECYCLE_RULES,
    )
    with pytest.raises(ValueError):
        ensure_transition_authorized(
            DocumentLifecycleStatus.PENDING_DELETE,
            DocumentLifecycleStatus.ACTIVE,
            StateActor.DELETION_SERVICE,
            DOCUMENT_LIFECYCLE_RULES,
        )


def test_active_published_version_survives_new_job_failure_in_ui() -> None:
    """中文：后台候选失败不能把仍有活动版本的文档展示为失败。

    English: A failed candidate job cannot make a document with an active version look failed.
    """

    status = derive_document_operational_status(
        DocumentLifecycleStatus.ACTIVE,
        DocumentVersionStatus.PUBLISHED,
        QualityDecision.PASS,
        JobExecutionStatus.FAILED,
    )
    assert status is DocumentOperationalStatus.READY


def test_version_servability_requires_every_gate() -> None:
    """中文：发布、质量、生命周期和撤销门禁必须全部通过。

    English: Publication, quality, lifecycle, and revocation gates must all pass.
    """

    assert is_version_servable(
        DocumentLifecycleStatus.ACTIVE,
        DocumentVersionStatus.PUBLISHED,
        QualityDecision.PASS_WITH_WARNINGS,
        False,
    )
    assert not is_version_servable(
        DocumentLifecycleStatus.ACTIVE,
        DocumentVersionStatus.PUBLISHED,
        QualityDecision.PASS,
        True,
    )
