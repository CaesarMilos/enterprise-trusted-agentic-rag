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


class LifecycleFenceError(ConflictError):
    """中文：报告任务持有的文档 generation 已失效，禁止任何后续写入或发布。

    English: Report that a job's document generation is stale and may no longer write or publish.
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
