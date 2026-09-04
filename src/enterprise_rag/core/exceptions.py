"""中文：本模块负责实现“异常”相关功能。

English: Define stable application exceptions without coupling the domain to HTTP.
"""

from __future__ import annotations

from dataclasses import dataclass

from enterprise_rag.core.enums import ErrorCategory


@dataclass(slots=True)
class ErrorDetail:
    """中文：该类用于表示或实现“错误详情（ErrorDetail）”的职责。

    English: Carry a machine-readable error code and safe diagnostic context.
    """

    # 中文：变量 `code` 用于保存“`code`”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable code exposed to API clients and traces.
    code: str
    # 中文：变量 `category` 用于保存“`category`”相关数据；其精确定义与约束见下方英文说明。
    # English: Broad category used for status mapping and metrics.
    category: ErrorCategory
    # 中文：变量 `message` 用于保存“消息”相关数据；其精确定义与约束见下方英文说明。
    # English: Human-readable message that must not contain secrets.
    message: str
    # 中文：变量 `context` 用于保存“上下文”相关数据；其精确定义与约束见下方英文说明。
    # English: Optional safe values that help operators diagnose the failure.
    context: dict[str, str] | None = None


class EnterpriseRAGError(Exception):
    """中文：该类用于表示或实现“企业RAG错误（EnterpriseRAGError）”的职责。

    English: Base class for expected business and infrastructure failures.
    """

    def __init__(self, detail: ErrorDetail) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store the structured error detail and initialize ``Exception``.
        """

        # 中文：变量 `detail` 用于保存“`detail`”相关数据；其精确定义与约束见下方英文说明。
        # English: Structured detail retained for API and trace adapters.
        self.detail = detail
        super().__init__(detail.message)


class ValidationError(EnterpriseRAGError):
    """中文：该类用于表示或实现“校验错误（ValidationError）”的职责。

    English: Report invalid input or invalid configuration.
    """


class NotFoundError(EnterpriseRAGError):
    """中文：该类用于表示或实现“不已找到错误（NotFoundError）”的职责。

    English: Report a requested entity that does not exist in the permitted scope.
    """


class PermissionDeniedError(EnterpriseRAGError):
    """中文：该类用于表示或实现“权限被拒绝的错误（PermissionDeniedError）”的职责。

    English: Report a request that exceeds the trusted user context.
    """


class ConflictError(EnterpriseRAGError):
    """中文：该类用于表示或实现“冲突错误（ConflictError）”的职责。

    English: Report a lifecycle or optimistic-concurrency conflict.
    """


class LeaseLostError(ConflictError):
    """中文：报告当前 Worker 已失去任务租约及写入权限。

    English: Report that the current worker lost its job lease and write authority.
    """


class LeaseOwnershipLostError(LeaseLostError):
    """中文：报告任务租约已经由另一个 Worker 或 generation 接管。

    English: Report that another worker or lease generation now owns the job.
    """


class LeaseExpiredError(LeaseLostError):
    """中文：报告当前 Worker 的任务租约已超过持久化到期时间。

    English: Report that the worker's durable job lease has expired.
    """


class LifecycleFenceError(ConflictError):
    """中文：报告任务持有的文档 generation 已失效，禁止任何后续写入或发布。

    English: Report that a job's document generation is stale and may no longer write or publish.
    """


class DocumentGenerationStaleError(LifecycleFenceError):
    """中文：报告任务创建时冻结的文档 generation 已失效。

    English: Report that the document generation frozen by the job is stale.
    """


class JobCancelledError(ConflictError):
    """中文：报告任务收到持久取消请求并在安全检查点停止。

    English: Report that a job observed a durable cancellation request at a safe checkpoint.
    """


class StaleIndexBuildPlanError(ConflictError):
    """中文：报告索引计划基于已经过期的活动索引快照。

    English: Report an index plan built from an obsolete active-index snapshot.
    """


class StorageError(EnterpriseRAGError):
    """中文：该类用于表示或实现“存储错误（StorageError）”的职责。

    English: Report a failure while reading or writing original document bytes.
    """


class ParsingError(EnterpriseRAGError):
    """中文：该类用于表示或实现“解析错误（ParsingError）”的职责。

    English: Report a document parsing failure.
    """


class ChunkValidationError(ParsingError):
    """中文：报告切块集合违反硬边界、完整性或父子关系发布门禁。

    English: Report that chunks violate hard-boundary, integrity, or hierarchy publication gates.
    """


class AuthenticationConfigurationError(ValidationError):
    """中文：报告认证模式、密钥或身份提供方配置不满足安全启动条件。

    English: Report authentication settings that fail secure-start requirements.
    """


class IndexBuildError(EnterpriseRAGError):
    """中文：该类用于表示或实现“索引构建错误（IndexBuildError）”的职责。

    English: Report failure to build or validate an immutable index snapshot.
    """


class RetrievalError(EnterpriseRAGError):
    """中文：该类用于表示或实现“检索错误（RetrievalError）”的职责。

    English: Report failure of every configured retrieval path.
    """


class ModelProviderError(EnterpriseRAGError):
    """中文：该类用于表示或实现“模型提供方错误（ModelProviderError）”的职责。

    English: Report a language, embedding, or reranker provider failure.
    """


class OperationTimeoutError(EnterpriseRAGError):
    """中文：该类用于表示或实现“操作超时错误（OperationTimeoutError）”的职责。

    English: Report that a bounded workflow exceeded its deadline.
    """


class InvalidStateTransitionError(ConflictError):
    """中文：报告领域状态机不允许请求的状态跃迁。

    English: Report a transition rejected by a domain state machine.
    """


class TransitionAuthorityError(PermissionDeniedError):
    """中文：报告调用组件无权修改目标状态机。

    English: Report that the calling component may not mutate the target state machine.
    """


class ContractValidationError(ValidationError):
    """中文：报告资料源内容契约缺少必需字段或违反不变量。

    English: Report a source contract missing required fields or violating invariants.
    """


class ProfileMismatchError(ValidationError):
    """中文：报告文档结构与资料源显式内容契约高置信度不匹配。

    English: Report a high-confidence mismatch with an explicit source content contract.
    """


class InvalidLocatorError(ValidationError):
    """中文：报告引用无法映射到合法原文或展示坐标。

    English: Report a citation that cannot map to a valid source or display location.
    """


class InvalidQuestionPlanError(ValidationError):
    """中文：报告问题计划违反信息需要、锚点或依赖约束。

    English: Report a question plan violating need, anchor, or dependency constraints.
    """


class InvalidEvidenceCoverageError(ValidationError):
    """中文：报告证据评分向量与问题计划不一致。

    English: Report evidence grades inconsistent with the question plan.
    """


class InvalidAnswerProtocolError(ValidationError):
    """中文：报告最终回答包含未验证 Claim、悬空引用或非法状态组合。

    English: Report unverified claims, dangling citations, or invalid answer-state combinations.
    """


class SnapshotExpiredError(ConflictError):
    """中文：报告查询知识快照已经超过最大租约时间。

    English: Report that a query knowledge snapshot exceeded its maximum lease time.
    """


class SnapshotRevokedError(PermissionDeniedError):
    """中文：报告固定快照中的资料源、文档或版本已被即时撤销。

    English: Report immediate revocation of a source, document, or version in a snapshot.
    """


class SnapshotScopeError(PermissionDeniedError):
    """中文：报告候选证据不属于请求固定的知识快照。

    English: Report candidate evidence outside the request's fixed knowledge snapshot.
    """


class MigrationStateError(EnterpriseRAGError):
    """中文：报告数据库迁移版本不满足安全启动或数据兼容要求。

    English: Report a database revision unsafe for startup or data compatibility.
    """


def error_detail(
    code: str,
    category: ErrorCategory,
    message: str,
    **context: str,
) -> ErrorDetail:
    """中文：该函数或方法负责“错误详情”相关处理。

    English: Build an :class:`ErrorDetail` while omitting an empty context mapping.
    """

    # 中文：变量 `safe_context` 用于保存“安全上下文”相关数据；其精确定义与约束见下方英文说明。
    # English: Optional diagnostic context, represented as ``None`` when empty.
    safe_context = context or None
    return ErrorDetail(code=code, category=category, message=message, context=safe_context)
