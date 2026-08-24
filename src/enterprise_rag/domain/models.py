"""中文：本模块负责实现“模型”相关功能。

English: Define immutable domain entities for tenancy, documents, indexes, citations, and
traces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from enterprise_rag.core.enums import (
    ContentProfile,
    DocumentStatus,
    IndexStatus,
    JobStatus,
    SourceVisibility,
)


def utc_now() -> datetime:
    """中文：该函数或方法负责“`utc`当前时间”相关处理。

    English: Return a timezone-aware UTC timestamp for domain defaults.
    """

    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class Tenant:
    """中文：该类用于表示或实现“租户（Tenant）”的职责。

    English: Represent one isolated customer organization.
    """

    # 中文：变量 `id` 用于保存“标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable tenant identifier used by every authorization boundary.
    id: str
    # 中文：变量 `name` 用于保存“`name`”相关数据；其精确定义与约束见下方英文说明。
    # English: Human-readable organization name.
    name: str
    # 中文：变量 `is_active` 用于保存“`is`活动”相关数据；其精确定义与约束见下方英文说明。
    # English: Whether the tenant may accept new application operations.
    is_active: bool = True
    # 中文：变量 `created_at` 用于保存“`created``at`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Creation timestamp used for auditing.
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class UserContext:
    """中文：该类用于表示或实现“用户上下文（UserContext）”的职责。

    English: Represent trusted identity and authorization data created by the authentication
    layer.
    """

    # 中文：变量 `user_id` 用于保存“用户标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable user or service-account identifier.
    user_id: str
    # 中文：变量 `tenant_id` 用于保存“租户标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Tenant to which every operation must remain scoped.
    tenant_id: str
    # 中文：变量 `roles` 用于保存“`roles`”相关数据；其精确定义与约束见下方英文说明。
    # English: Named roles granted by the trusted identity provider.
    roles: frozenset[str] = frozenset()
    # 中文：变量 `allowed_source_ids` 用于保存“`allowed`资料源标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Explicit source identifiers visible to this user.
    allowed_source_ids: frozenset[str] = frozenset()
    # 中文：变量 `group_ids` 用于保存“`group`标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Optional group identifiers used by restricted sources.
    group_ids: frozenset[str] = frozenset()

    def is_admin(self) -> bool:
        """中文：该函数或方法负责“为管理员”相关处理。

        English: Return whether the trusted identity contains the tenant administrator role.
        """

        return "admin" in self.roles


@dataclass(frozen=True, slots=True)
class RetrievalScope:
    """中文：该类用于表示或实现“检索范围（RetrievalScope）”的职责。

    English: Freeze the exact tenant, sources, documents, and index version allowed for
    retrieval.
    """

    # 中文：变量 `tenant_id` 用于保存“租户标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Tenant identifier applied to every candidate filter.
    tenant_id: str
    # 中文：变量 `source_ids` 用于保存“资料源标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Sources authorized before routing and search begin.
    source_ids: frozenset[str]
    # 中文：变量 `document_ids` 用于保存“文档标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Optional document allow-list; an empty set means every active document in
    #   the sources.
    document_ids: frozenset[str] = frozenset()
    # 中文：变量 `index_version_id` 用于保存“索引版本标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Immutable index snapshot selected at the start of the request.
    index_version_id: str | None = None

    def allows(self, tenant_id: str, source_id: str, document_id: str) -> bool:
        """中文：该函数或方法负责“允许”相关处理。

        English: Return whether a candidate belongs to this exact precomputed scope.
        """

        # 中文：变量 `document_allowed` 用于保存“文档`allowed`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Document allow-list is only restrictive when it contains explicit
        #   identifiers.
        document_allowed = not self.document_ids or document_id in self.document_ids
        return tenant_id == self.tenant_id and source_id in self.source_ids and document_allowed


@dataclass(frozen=True, slots=True)
class Source:
    """中文：该类用于表示或实现“资料源（Source）”的职责。

    English: Represent a routable collection of related enterprise documents.
    """

    # 中文：变量 `id` 用于保存“标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable source identifier.
    id: str
    # 中文：变量 `tenant_id` 用于保存“租户标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Owning tenant identifier.
    tenant_id: str
    # 中文：变量 `name` 用于保存“`name`”相关数据；其精确定义与约束见下方英文说明。
    # English: Display name used by administration and citations.
    name: str
    # 中文：变量 `description` 用于保存“`description`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Short description embedded or tokenized for automatic routing.
    description: str
    # 中文：管理员声明的主要内容类型，决定结构识别与切块策略。
    # English: Administrator-declared content type selecting structure and chunk strategy.
    content_profile: ContentProfile = ContentProfile.GENERAL_PROSE
    # 中文：可选高级策略覆盖；为空时由内容画像通过注册表自动解析。
    # English: Optional advanced override; empty values resolve through the profile registry.
    chunk_strategy_override: str | None = None
    # 中文：变量 `visibility` 用于保存“`visibility`”相关数据；其精确定义与约束见下方英文说明。
    # English: Access model enforced before source routing.
    visibility: SourceVisibility = SourceVisibility.TENANT
    # 中文：变量 `allowed_group_ids` 用于保存“`allowed``group`标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Groups permitted when visibility is restricted.
    allowed_group_ids: frozenset[str] = frozenset()
    # 中文：变量 `is_active` 用于保存“`is`活动”相关数据；其精确定义与约束见下方英文说明。
    # English: Whether the source may appear in newly created retrieval scopes.
    is_active: bool = True
    # 中文：变量 `created_at` 用于保存“`created``at`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Creation timestamp used for auditing.
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class Document:
    """中文：该类用于表示或实现“文档（Document）”的职责。

    English: Represent the mutable lifecycle of one logical document.
    """

    # 中文：变量 `id` 用于保存“标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable logical document identifier shared by all versions.
    id: str
    # 中文：变量 `tenant_id` 用于保存“租户标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Owning tenant identifier.
    tenant_id: str
    # 中文：变量 `source_id` 用于保存“资料源标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Parent source used by routing and authorization.
    source_id: str
    # 中文：变量 `title` 用于保存“标题”相关数据；其精确定义与约束见下方英文说明。
    # English: Safe user-facing filename or title.
    title: str
    # 中文：变量 `status` 用于保存“状态”相关数据；其精确定义与约束见下方英文说明。
    # English: Current lifecycle state.
    status: DocumentStatus = DocumentStatus.PENDING
    # 中文：变量 `active_version_id` 用于保存“活动版本标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Active immutable document version, if ingestion has completed.
    active_version_id: str | None = None
    # 中文：变量 `created_at` 用于保存“`created``at`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Creation timestamp used for auditing.
    created_at: datetime = field(default_factory=utc_now)
    # 中文：变量 `updated_at` 用于保存“`updated``at`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Last lifecycle change timestamp.
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class DocumentVersion:
    """中文：该类用于表示或实现“文档版本（DocumentVersion）”的职责。

    English: Represent one immutable upload or update of a logical document.
    """

    # 中文：变量 `id` 用于保存“标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable document-version identifier.
    id: str
    # 中文：变量 `tenant_id` 用于保存“租户标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Owning tenant identifier.
    tenant_id: str
    # 中文：变量 `document_id` 用于保存“文档标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Logical parent document identifier.
    document_id: str
    # 中文：变量 `source_id` 用于保存“资料源标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Parent source copied for permission-safe queries.
    source_id: str
    # 中文：变量 `version_number` 用于保存“版本`number`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Monotonically increasing version number within the logical document.
    version_number: int
    # 中文：变量 `original_filename` 用于保存“原始`filename`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Original filename retained for display, never used directly as a storage
    #   path.
    original_filename: str
    # 中文：变量 `media_type` 用于保存“`media``type`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Verified lowercase document type.
    media_type: str
    # 中文：变量 `content_hash` 用于保存“`content``hash`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: SHA-256 checksum of the original bytes.
    content_hash: str
    # 中文：变量 `storage_key` 用于保存“存储`key`”相关数据；其精确定义与约束见下方英文说明。
    # English: Opaque storage key returned by the file store.
    storage_key: str
    # 中文：变量 `size_bytes` 用于保存“`size``bytes`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Original byte length.
    size_bytes: int
    # 中文：变量 `content_profile` 冻结任务创建时的资料源内容画像。
    # English: `content_profile` freezes the source profile selected when the job is created.
    content_profile: ContentProfile = ContentProfile.GENERAL_PROSE
    # 中文：变量 `chunk_strategy_id` 冻结已解析的策略标识，避免排队期间配置漂移。
    # English: `chunk_strategy_id` freezes the resolved strategy against queue-time drift.
    chunk_strategy_id: str = "general-prose"
    # 中文：变量 `chunk_strategy_version` 冻结实际算法版本，支持确定性重处理和审计。
    # English: `chunk_strategy_version` freezes the algorithm version for reproducible reprocessing.
    chunk_strategy_version: str = "general-prose-v2"
    # 中文：变量 `chunk_parameters` 保存创建版本时生效的关键切块参数快照。
    # English: `chunk_parameters` stores the effective chunk-parameter snapshot.
    chunk_parameters: dict[str, Any] = field(default_factory=dict)
    # 中文：变量 `embedding_fingerprint` 标识语义边界和索引使用的向量模型。
    # English: `embedding_fingerprint` identifies the model used by semantic boundaries and index.
    embedding_fingerprint: str = ""
    # 中文：变量 `boundary_model_fingerprint` 记录可选 LLM 边界复核模型与提示词版本。
    # English: `boundary_model_fingerprint` records the optional LLM reviewer and prompt version.
    boundary_model_fingerprint: str | None = None
    # 中文：变量 `quality_metrics` 保存接入质量门输出，供管理界面和回归评估使用。
    # English: `quality_metrics` persists the quality-gate output for administration and regression.
    quality_metrics: dict[str, Any] = field(default_factory=dict)
    # 中文：变量 `created_at` 用于保存“`created``at`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Creation timestamp used for auditing and version ordering.
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class Chunk:
    """中文：该类用于表示或实现“文本块（Chunk）”的职责。

    English: Represent one deterministic, citable piece of an immutable document version.
    """

    # 中文：变量 `id` 用于保存“标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Deterministic chunk identifier.
    id: str
    # 中文：变量 `tenant_id` 用于保存“租户标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Owning tenant identifier copied for direct ACL filtering.
    tenant_id: str
    # 中文：变量 `source_id` 用于保存“资料源标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Parent source identifier copied for routing and ACL filtering.
    source_id: str
    # 中文：变量 `document_id` 用于保存“文档标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Logical document identifier.
    document_id: str
    # 中文：变量 `document_version_id` 用于保存“文档版本标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Immutable document-version identifier.
    document_version_id: str
    # 中文：变量 `ordinal` 用于保存“`ordinal`”相关数据；其精确定义与约束见下方英文说明。
    # English: Zero-based position within the prepared document.
    ordinal: int
    # 中文：变量 `text` 用于保存“文本”相关数据；其精确定义与约束见下方英文说明。
    # English: Clean text supplied to embedding, lexical search, and answer context.
    text: str
    # 中文：变量 `token_count` 用于保存“词元`count`”相关数据；其精确定义与约束见下方英文说明。
    # English: Token estimate used by chunk and context budgets.
    token_count: int
    # 中文：变量 `page_start` 用于保存“`page``start`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: First page represented by the chunk, when the format supplies pages.
    page_start: int | None
    # 中文：变量 `page_end` 用于保存“`page``end`”相关数据；其精确定义与约束见下方英文说明。
    # English: Last page represented by the chunk, when the format supplies pages.
    page_end: int | None
    # 中文：变量 `heading_path` 用于保存“`heading``path`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Hierarchical section names from outermost to innermost.
    heading_path: tuple[str, ...]
    # 中文：变量 `previous_chunk_id` 用于保存“`previous`文本块标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Deterministic identifier of the previous chunk in this version.
    previous_chunk_id: str | None
    # 中文：变量 `next_chunk_id` 用于保存“下一个文本块标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Deterministic identifier of the next chunk in this version.
    next_chunk_id: str | None
    # 中文：变量 `boundary_reason` 用于保存“`boundary`原因”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Explanation of the boundary selected by the chunker.
    boundary_reason: str
    # 中文：变量 `chunker_version` 用于保存“切块器版本”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Chunker algorithm version included in deterministic identity.
    chunker_version: str
    # 中文：变量 `content_hash` 用于保存“`content``hash`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: SHA-256 checksum of normalized chunk text.
    content_hash: str
    # 中文：变量 `retrieval_text` 将标题路径和规范化编号注入索引文本，不改变引用正文。
    # English: `retrieval_text` injects headings and normalized identifiers without altering
    # citations.
    retrieval_text: str = ""
    # 中文：变量 `parent_chunk_id` 指向更宽上下文父块；父块本身为空。
    # English: `parent_chunk_id` points to a broader context chunk and is empty for parents.
    parent_chunk_id: str | None = None
    # 中文：变量 `chunk_level` 区分可精确引用的叶子块与用于扩展上下文的父块。
    # English: `chunk_level` distinguishes precise leaves from broader parent context.
    chunk_level: str = "leaf"
    # 中文：变量 `unit_type` 保存该块的主要结构类型，如条款、步骤或警告。
    # English: `unit_type` stores the dominant structure, such as clause, step, or warning.
    unit_type: str = "prose"
    # 中文：变量 `section_number` 保存可精确检索的条款、章节或步骤编号。
    # English: `section_number` stores an exactly retrievable clause, chapter, or step identifier.
    section_number: str | None = None
    # 中文：变量 `source_start_offset` 是清洗后文档中的起始字符位置。
    # English: `source_start_offset` is the start character position in normalized source text.
    source_start_offset: int = 0
    # 中文：变量 `source_end_offset` 是清洗后文档中的结束字符位置。
    # English: `source_end_offset` is the end character position in normalized source text.
    source_end_offset: int = 0
    # 中文：变量 `boundary_method` 保存最终边界算法来源。
    # English: `boundary_method` records the algorithm that committed this boundary.
    boundary_method: str = "deterministic"
    # 中文：变量 `boundary_confidence` 保存零到一之间的边界判定置信度。
    # English: `boundary_confidence` stores boundary certainty in the zero-to-one range.
    boundary_confidence: float = 1.0
    # 中文：变量 `metadata` 用于保存“元数据”相关数据；其精确定义与约束见下方英文说明。
    # English: Additional format-specific values that are safe to index.
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class IngestionJob:
    """中文：该类用于表示或实现“资料接入任务（IngestionJob）”的职责。

    English: Represent a durable, recoverable background ingestion task.
    """

    # 中文：变量 `id` 用于保存“标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable job identifier returned by the asynchronous upload API.
    id: str
    # 中文：变量 `tenant_id` 用于保存“租户标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Owning tenant identifier.
    tenant_id: str
    # 中文：变量 `document_id` 用于保存“文档标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Logical document being processed.
    document_id: str
    # 中文：变量 `document_version_id` 用于保存“文档版本标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Immutable document version being processed.
    document_version_id: str
    # 中文：变量 `status` 用于保存“状态”相关数据；其精确定义与约束见下方英文说明。
    # English: Durable task state.
    status: JobStatus = JobStatus.PENDING
    # 中文：变量 `attempt_count` 用于保存“`attempt``count`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Number of worker claims, including the current attempt.
    attempt_count: int = 0
    # 中文：变量 `lease_owner` 用于保存“`lease``owner`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Worker identity holding the current lease.
    lease_owner: str | None = None
    # 中文：变量 `lease_expires_at` 用于保存“`lease``expires``at`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: UTC time at which another worker may recover the task.
    lease_expires_at: datetime | None = None
    # 中文：变量 `error_code` 用于保存“错误`code`”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable failure code safe to expose to administrators.
    error_code: str | None = None
    # 中文：变量 `error_message` 用于保存“错误消息”相关数据；其精确定义与约束见下方英文说明。
    # English: Redacted failure message safe to expose to administrators.
    error_message: str | None = None
    # 中文：变量 `created_at` 用于保存“`created``at`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Creation timestamp used for FIFO task ordering.
    created_at: datetime = field(default_factory=utc_now)
    # 中文：变量 `updated_at` 用于保存“`updated``at`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Last durable state-change timestamp.
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class JobFence:
    """中文：标识某个 Worker 对接入任务的一次唯一租约代次。

    English: Identify one unique worker lease generation for an ingestion job.
    """

    # 中文：变量 `tenant_id` 将 fencing 校验限制在所属租户内。
    # English: `tenant_id` scopes every fencing check to the owning tenant.
    tenant_id: str
    # 中文：变量 `job_id` 指向被当前 Worker 执行的持久任务。
    # English: `job_id` identifies the durable job executed by the current worker.
    job_id: str
    # 中文：变量 `lease_owner` 是领取本代任务的稳定 Worker 标识。
    # English: `lease_owner` is the stable identity that claimed this generation.
    lease_owner: str
    # 中文：变量 `attempt_count` 是每次重新领取递增的 fencing generation。
    # English: `attempt_count` is the fencing generation incremented on every claim.
    attempt_count: int


def job_fence_from_job(job: IngestionJob) -> JobFence:
    """中文：从已领取的运行中任务生成不可变 fencing token。

    English: Build an immutable fencing token from a claimed running job.
    """

    if job.status is not JobStatus.RUNNING or not job.lease_owner:
        raise ValueError("only a leased running job can create a fence")
    if job.attempt_count < 1:
        raise ValueError("a job fence requires a positive attempt count")
    return JobFence(
        tenant_id=job.tenant_id,
        job_id=job.id,
        lease_owner=job.lease_owner,
        attempt_count=job.attempt_count,
    )


@dataclass(frozen=True, slots=True)
class IndexVersion:
    """中文：该类用于表示或实现“索引版本（IndexVersion）”的职责。

    English: Represent the database publication record for one immutable index snapshot.
    """

    # 中文：变量 `id` 用于保存“标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable index version identifier.
    id: str
    # 中文：变量 `tenant_id` 用于保存“租户标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Owning tenant identifier.
    tenant_id: str
    # 中文：变量 `status` 用于保存“状态”相关数据；其精确定义与约束见下方英文说明。
    # English: Staging, ready, active, retired, or failed publication state.
    status: IndexStatus
    # 中文：变量 `storage_key` 用于保存“存储`key`”相关数据；其精确定义与约束见下方英文说明。
    # English: Opaque snapshot directory name beneath the tenant index root.
    storage_key: str
    # 中文：变量 `chunk_count` 用于保存“文本块`count`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Number of chunks represented by every component.
    chunk_count: int
    # 中文：变量 `config_fingerprint` 用于保存“配置指纹”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Configuration and model fingerprint.
    config_fingerprint: str
    # 中文：变量 `created_at` 用于保存“`created``at`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Creation timestamp used for retention ordering.
    created_at: datetime = field(default_factory=utc_now)
    # 中文：变量 `activated_at` 用于保存“`activated``at`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Activation timestamp, present only after transactional publication.
    activated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class IndexManifest:
    """中文：该类用于表示或实现“索引清单（IndexManifest）”的职责。

    English: Describe and verify every file belonging to an immutable index snapshot.
    """

    # 中文：变量 `index_version_id` 用于保存“索引版本标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Index version to which the manifest belongs.
    index_version_id: str
    # 中文：变量 `tenant_id` 用于保存“租户标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Owning tenant identifier.
    tenant_id: str
    # 中文：变量 `chunk_ids` 用于保存“文本块标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Chunk IDs in the exact order used by dense and lexical components.
    chunk_ids: tuple[str, ...]
    # 中文：变量 `embedding_fingerprint` 用于保存“向量嵌入指纹”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Embedding provider and model fingerprint.
    embedding_fingerprint: str
    # 中文：变量 `chunker_version` 用于保存“切块器版本”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Chunker algorithm version.
    chunker_version: str
    # 中文：变量 `config_fingerprint` 用于保存“配置指纹”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Configuration fingerprint used for reproducibility.
    config_fingerprint: str
    # 中文：变量 `artifact_checksums` 用于保存“制品`checksums`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Relative artifact path to SHA-256 checksum mapping.
    artifact_checksums: dict[str, str]
    # 中文：变量 `created_at` 用于保存“`created``at`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: UTC timestamp at which the manifest was finalized.
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class Citation:
    """中文：该类用于表示或实现“引用（Citation）”的职责。

    English: Represent one verified answer citation to an authorized immutable chunk.
    """

    # 中文：变量 `citation_id` 用于保存“引用标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable display identifier such as C1.
    citation_id: str
    # 中文：变量 `chunk_id` 用于保存“文本块标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Referenced deterministic chunk identifier.
    chunk_id: str
    # 中文：变量 `document_id` 用于保存“文档标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Logical document identifier.
    document_id: str
    # 中文：变量 `document_version_id` 用于保存“文档版本标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Immutable document-version identifier.
    document_version_id: str
    # 中文：变量 `source_id` 用于保存“资料源标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Source identifier used for permission revalidation.
    source_id: str
    # 中文：变量 `title` 用于保存“标题”相关数据；其精确定义与约束见下方英文说明。
    # English: Display title included in API output.
    title: str
    # 中文：变量 `page_start` 用于保存“`page``start`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: First cited page when available.
    page_start: int | None
    # 中文：变量 `page_end` 用于保存“`page``end`”相关数据；其精确定义与约束见下方英文说明。
    # English: Last cited page when available.
    page_end: int | None
    # 中文：变量 `excerpt` 用于保存“`excerpt`”相关数据；其精确定义与约束见下方英文说明。
    # English: Optional short evidence excerpt.
    excerpt: str | None = None


@dataclass(frozen=True, slots=True)
class TraceRecord:
    """中文：该类用于表示或实现“追踪记录（TraceRecord）”的职责。

    English: Represent the redacted summary of one observable application workflow.
    """

    # 中文：变量 `id` 用于保存“标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable trace identifier shared across logs and public results.
    id: str
    # 中文：变量 `tenant_id` 用于保存“租户标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Owning tenant identifier.
    tenant_id: str
    # 中文：变量 `user_id` 用于保存“用户标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Requesting user identifier used by trace authorization.
    user_id: str
    # 中文：变量 `operation` 用于保存“`operation`”相关数据；其精确定义与约束见下方英文说明。
    # English: Workflow type such as chat, ingestion, or index-build.
    operation: str
    # 中文：变量 `status` 用于保存“状态”相关数据；其精确定义与约束见下方英文说明。
    # English: Final workflow status.
    status: str
    # 中文：变量 `index_version_id` 用于保存“索引版本标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Immutable index snapshot used by the request, when applicable.
    index_version_id: str | None = None
    # 中文：变量 `attributes` 用于保存“`attributes`”相关数据；其精确定义与约束见下方英文说明。
    # English: Safe structured measurements and decisions.
    attributes: dict[str, Any] = field(default_factory=dict)
    # 中文：变量 `created_at` 用于保存“`created``at`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Creation timestamp for trace ordering.
    created_at: datetime = field(default_factory=utc_now)
    # 中文：变量 `completed_at` 用于保存“`completed``at`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Completion timestamp when the workflow reaches a terminal state.
    completed_at: datetime | None = None
