"""中文：本模块负责实现“请求”相关功能。

English: Define framework-independent commands and queries accepted by application services.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from enterprise_rag.domain.models import UserContext


@dataclass(frozen=True, slots=True)
class CreateDocumentCommand:
    """中文：该类用于表示或实现“创建文档命令（CreateDocumentCommand）”的职责。

    English: Request durable ingestion of one local upload into a source.
    """

    # 中文：变量 `user` 用于保存“用户”相关数据；其精确定义与约束见下方英文说明。
    # English: Trusted caller context.
    user: UserContext
    # 中文：变量 `source_id` 用于保存“资料源标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Existing source that should own the document.
    source_id: str
    # 中文：变量 `filename` 用于保存“`filename`”相关数据；其精确定义与约束见下方英文说明。
    # English: Safe original filename used for display and type validation.
    filename: str
    # 中文：变量 `temporary_path` 用于保存“`temporary``path`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Temporary local path supplied by the delivery adapter.
    temporary_path: Path
    # 中文：变量 `title` 用于保存“标题”相关数据；其精确定义与约束见下方英文说明。
    # English: Optional title overriding the original filename.
    title: str | None = None


@dataclass(frozen=True, slots=True)
class DeleteDocumentCommand:
    """中文：该类用于表示或实现“删除文档命令（DeleteDocumentCommand）”的职责。

    English: Request permission-safe asynchronous removal of one logical document.
    """

    # 中文：变量 `user` 用于保存“用户”相关数据；其精确定义与约束见下方英文说明。
    # English: Trusted caller context.
    user: UserContext
    # 中文：变量 `document_id` 用于保存“文档标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Logical document to exclude and remove.
    document_id: str


@dataclass(frozen=True, slots=True)
class RetryIngestionCommand:
    """中文：该类用于表示或实现“重试资料接入命令（RetryIngestionCommand）”的职责。

    English: Request another durable attempt for a failed document version.
    """

    # 中文：变量 `user` 用于保存“用户”相关数据；其精确定义与约束见下方英文说明。
    # English: Trusted administrator context.
    user: UserContext
    # 中文：变量 `document_id` 用于保存“文档标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Failed logical document.
    document_id: str
    # 中文：可选幂等键使网络重试返回同一后台任务。
    # English: Optional idempotency key makes network retries return the same background job.
    idempotency_key: str | None = None


@dataclass(frozen=True, slots=True)
class ReprocessDocumentCommand:
    """中文：请求使用资料源当前内容画像重新解析并切割已有原始文件。

    English: Request reprocessing an original file with the source's current content profile.
    """

    # 中文：仅租户管理员可以创建新的处理版本。
    # English: Only tenant administrators may create a new processing version.
    user: UserContext
    # 中文：待重新处理的逻辑文档标识符。
    # English: Logical document identifier to reprocess.
    document_id: str
    # 中文：可选幂等键阻止重复点击创建多个候选版本。
    # English: Optional idempotency key prevents repeated clicks creating duplicate candidates.
    idempotency_key: str | None = None


@dataclass(frozen=True, slots=True)
class RebuildIndexCommand:
    """中文：该类用于表示或实现“重建索引命令（RebuildIndexCommand）”的职责。

    English: Request construction and publication of a fresh tenant index snapshot.
    """

    # 中文：变量 `user` 用于保存“用户”相关数据；其精确定义与约束见下方英文说明。
    # English: Trusted administrator context.
    user: UserContext
    # 中文：变量 `reason` 用于保存“原因”相关数据；其精确定义与约束见下方英文说明。
    # English: Optional reason stored in trace metadata.
    reason: str = "manual"


@dataclass(frozen=True, slots=True)
class ChatCommand:
    """中文：该类用于表示或实现“问答命令（ChatCommand）”的职责。

    English: Request an evidence-grounded answer within the caller's authorized scope.
    """

    # 中文：变量 `user` 用于保存“用户”相关数据；其精确定义与约束见下方英文说明。
    # English: Trusted caller context.
    user: UserContext
    # 中文：变量 `query` 用于保存“查询”相关数据；其精确定义与约束见下方英文说明。
    # English: Natural-language question.
    query: str
    # 中文：变量 `conversation_id` 用于保存“`conversation`标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Optional conversation identifier for client-side continuity.
    conversation_id: str | None = None
    # 中文：变量 `requested_source_ids` 用于保存“请求的资料源标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Optional source restriction that must be intersected with authorized sources.
    requested_source_ids: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class TraceQuery:
    """中文：该类用于表示或实现“追踪查询（TraceQuery）”的职责。

    English: Request a permission-aware public or administrator trace view.
    """

    # 中文：变量 `user` 用于保存“用户”相关数据；其精确定义与约束见下方英文说明。
    # English: Trusted caller context.
    user: UserContext
    # 中文：变量 `trace_id` 用于保存“追踪标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Trace to retrieve.
    trace_id: str


@dataclass(frozen=True, slots=True)
class EvaluationCommand:
    """中文：该类用于表示或实现“评估命令（EvaluationCommand）”的职责。

    English: Request a reproducible evaluation against fixed artifacts and configuration.
    """

    # 中文：变量 `user` 用于保存“用户”相关数据；其精确定义与约束见下方英文说明。
    # English: Trusted administrator context.
    user: UserContext
    # 中文：变量 `dataset_path` 用于保存“评估集`path`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Versioned evaluation dataset path.
    dataset_path: Path
    # 中文：变量 `index_version_id` 用于保存“索引版本标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Immutable index snapshot under evaluation.
    index_version_id: str
    # 中文：变量 `report_dir` 用于保存“`report``dir`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Output directory for machine-readable and Markdown reports.
    report_dir: Path
