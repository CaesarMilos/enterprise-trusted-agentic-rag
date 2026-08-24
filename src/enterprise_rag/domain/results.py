"""中文：本模块负责实现“结果”相关功能。

English: Define stable framework-independent results returned by application services.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from enterprise_rag.core.enums import RefusalReason
from enterprise_rag.domain.models import Citation


@dataclass(frozen=True, slots=True)
class IngestionAccepted:
    """中文：该类用于表示或实现“资料接入已接受（IngestionAccepted）”的职责。

    English: Confirm that upload bytes and a durable ingestion job were created.
    """

    # 中文：变量 `document_id` 用于保存“文档标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Logical document identifier.
    document_id: str
    # 中文：变量 `document_version_id` 用于保存“文档版本标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Immutable version identifier.
    document_version_id: str
    # 中文：变量 `job_id` 用于保存“任务标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Durable background job identifier.
    job_id: str
    # 中文：变量 `status` 用于保存“状态”相关数据；其精确定义与约束见下方英文说明。
    # English: Public initial document state.
    status: str


@dataclass(frozen=True, slots=True)
class DocumentDetail:
    """中文：该类用于表示或实现“文档详情（DocumentDetail）”的职责。

    English: Expose permission-safe document lifecycle information.
    """

    # 中文：变量 `document_id` 用于保存“文档标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Logical document identifier.
    document_id: str
    # 中文：变量 `source_id` 用于保存“资料源标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Parent source identifier.
    source_id: str
    # 中文：变量 `title` 用于保存“标题”相关数据；其精确定义与约束见下方英文说明。
    # English: Human-readable title.
    title: str
    # 中文：变量 `status` 用于保存“状态”相关数据；其精确定义与约束见下方英文说明。
    # English: Current lifecycle state.
    status: str
    # 中文：变量 `active_version_id` 用于保存“活动版本标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Active immutable version, when ready.
    active_version_id: str | None
    # 中文：变量 `error_code` 用于保存“错误`code`”相关数据；其精确定义与约束见下方英文说明。
    # English: Most recent safe ingestion failure code.
    error_code: str | None = None
    # 中文：变量 `content_profile` 展示活动版本冻结的资料源画像。
    # English: `content_profile` exposes the active version's frozen source profile.
    content_profile: str | None = None
    # 中文：变量 `chunk_strategy_version` 展示实际切块算法版本。
    # English: `chunk_strategy_version` exposes the exact chunk algorithm version.
    chunk_strategy_version: str | None = None
    # 中文：变量 `quality_metrics` 展示持久化的接入质量门指标。
    # English: `quality_metrics` exposes persisted ingestion quality-gate measurements.
    quality_metrics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class IndexBuildResult:
    """中文：该类用于表示或实现“索引构建结果（IndexBuildResult）”的职责。

    English: Describe the outcome of immutable index construction and publication.
    """

    # 中文：变量 `index_version_id` 用于保存“索引版本标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Newly constructed index version.
    index_version_id: str
    # 中文：变量 `chunk_count` 用于保存“文本块`count`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Number of chunks represented by all index components.
    chunk_count: int
    # 中文：变量 `activated` 用于保存“`activated`”相关数据；其精确定义与约束见下方英文说明。
    # English: Whether the snapshot became the tenant's active version.
    activated: bool
    # 中文：变量 `previous_index_version_id` 用于保存“`previous`索引版本标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Optional prior active version retained for safe rollback.
    previous_index_version_id: str | None


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    """中文：该类用于表示或实现“检索结果（RetrievalResult）”的职责。

    English: Expose explainable retrieval output to the agent workflow.
    """

    # 中文：变量 `index_version_id` 用于保存“索引版本标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Immutable index snapshot used for every retrieval component.
    index_version_id: str
    # 中文：变量 `chunk_ids` 用于保存“文本块标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Selected deterministic chunk identifiers in final context order.
    chunk_ids: tuple[str, ...]
    # 中文：变量 `decisions` 用于保存“`decisions`”相关数据；其精确定义与约束见下方英文说明。
    # English: Public routing and Top-K explanation.
    decisions: dict[str, Any]
    # 中文：变量 `degradations` 用于保存“`degradations`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Safe degradation labels such as dense_unavailable.
    degradations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AnswerResult:
    """中文：该类用于表示或实现“答案结果（AnswerResult）”的职责。

    English: Expose a verified evidence-grounded answer.
    """

    # 中文：变量 `trace_id` 用于保存“追踪标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable request trace identifier.
    trace_id: str
    # 中文：变量 `answer` 用于保存“答案”相关数据；其精确定义与约束见下方英文说明。
    # English: Verified answer text.
    answer: str
    # 中文：变量 `citations` 用于保存“引用”相关数据；其精确定义与约束见下方英文说明。
    # English: Verified citations in display order.
    citations: tuple[Citation, ...]
    # 中文：变量 `index_version_id` 用于保存“索引版本标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Immutable index snapshot used for the full workflow.
    index_version_id: str
    # 中文：变量 `retrieval_rounds` 用于保存“检索`rounds`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Number of retrieval attempts, including the initial attempt.
    retrieval_rounds: int


@dataclass(frozen=True, slots=True)
class RefusalResult:
    """中文：该类用于表示或实现“拒答结果（RefusalResult）”的职责。

    English: Expose an intentional refusal distinct from an infrastructure error.
    """

    # 中文：变量 `trace_id` 用于保存“追踪标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable request trace identifier.
    trace_id: str
    # 中文：变量 `reason` 用于保存“原因”相关数据；其精确定义与约束见下方英文说明。
    # English: Machine-readable refusal reason.
    reason: RefusalReason
    # 中文：变量 `message` 用于保存“消息”相关数据；其精确定义与约束见下方英文说明。
    # English: Safe user-facing explanation.
    message: str
    # 中文：变量 `index_version_id` 用于保存“索引版本标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Immutable index snapshot used when retrieval occurred.
    index_version_id: str | None = None


@dataclass(frozen=True, slots=True)
class TraceView:
    """中文：该类用于表示或实现“追踪视图（TraceView）”的职责。

    English: Expose a redacted trace projection appropriate to the requesting user.
    """

    # 中文：变量 `trace_id` 用于保存“追踪标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable trace identifier.
    trace_id: str
    # 中文：变量 `status` 用于保存“状态”相关数据；其精确定义与约束见下方英文说明。
    # English: Final workflow status.
    status: str
    # 中文：变量 `steps` 用于保存“`steps`”相关数据；其精确定义与约束见下方英文说明。
    # English: Ordered safe step summaries.
    steps: tuple[dict[str, Any], ...]
    # 中文：变量 `metrics` 用于保存“指标”相关数据；其精确定义与约束见下方英文说明。
    # English: Safe aggregate measurements.
    metrics: dict[str, float | int | str]


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    """中文：该类用于表示或实现“评估报告（EvaluationReport）”的职责。

    English: Expose reproducible evaluation metadata and metric groups.
    """

    # 中文：变量 `dataset_version` 用于保存“评估集版本”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Version identifier of the evaluated dataset.
    dataset_version: str
    # 中文：变量 `index_version_id` 用于保存“索引版本标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Immutable evaluated index version.
    index_version_id: str
    # 中文：变量 `fingerprints` 用于保存“`fingerprints`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Fingerprints needed to reproduce the result.
    fingerprints: dict[str, str]
    # 中文：变量 `metrics` 用于保存“指标”相关数据；其精确定义与约束见下方英文说明。
    # English: Named groups of computed metrics.
    metrics: dict[str, dict[str, float]]
