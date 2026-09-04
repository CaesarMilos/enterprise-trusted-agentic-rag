"""中文：定义与任务状态分离的不可变摄取质量报告。

English: Define immutable ingestion quality reports separated from job execution states.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from enterprise_rag.core.enums import QualityDecision


@dataclass(frozen=True, slots=True)
class QualityFinding:
    """中文：保存一条稳定、可审计的质量发现。

    English: Store one stable and auditable quality finding.
    """

    code: str
    severity: str
    message: str

    def __post_init__(self) -> None:
        """中文：限制严重级别和面向管理员的安全消息。

        English: Restrict severity and require a safe administrator-facing message.
        """

        if self.severity not in {"info", "warning", "error"}:
            raise ValueError("quality finding severity must be info, warning, or error")
        if not self.code or not self.message:
            raise ValueError("quality finding requires a code and message")


@dataclass(frozen=True, slots=True)
class IngestionQualityReport:
    """中文：保存一个文档版本的质量结论、指标和降级事实。

    English: Store quality decision, metrics, and degradation facts for one document version.
    """

    id: str
    tenant_id: str
    document_id: str
    document_version_id: str
    decision: QualityDecision
    validator_version: str
    created_at: datetime
    metrics: dict[str, Any] = field(default_factory=dict)
    findings: tuple[QualityFinding, ...] = ()
    degradation_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """中文：校验报告身份并防止 FAIL 结论缺少错误发现。

        English: Validate report identity and prevent a FAIL decision without an error finding.
        """

        if not all(
            (
                self.id,
                self.tenant_id,
                self.document_id,
                self.document_version_id,
                self.validator_version,
            )
        ):
            raise ValueError("quality report requires all identity and validator fields")
        if self.decision is QualityDecision.FAIL:
            if not any(finding.severity == "error" for finding in self.findings):
                raise ValueError("failed quality report requires at least one error finding")
