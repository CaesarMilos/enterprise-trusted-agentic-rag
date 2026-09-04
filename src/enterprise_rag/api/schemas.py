"""中文：本模块负责实现“数据结构”相关功能。

English: Define stable Pydantic request and response schemas for the HTTP boundary.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from enterprise_rag.core.enums import ContentProfile


class APISchema(BaseModel):
    """中文：该类用于表示或实现“接口数据结构（APISchema）”的职责。

    English: Provide strict public-schema behavior shared by all API models.
    """

    model_config = ConfigDict(extra="forbid")


class CitationSchema(APISchema):
    """中文：该类用于表示或实现“引用数据结构（CitationSchema）”的职责。

    English: Expose one verified citation and source position.
    """

    # 中文：变量 `citation_id` 用于保存“引用标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable display label.
    citation_id: str
    # 中文：变量 `chunk_id` 用于保存“文本块标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Deterministic chunk identifier.
    chunk_id: str
    # 中文：变量 `document_id` 用于保存“文档标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Logical document identifier.
    document_id: str
    # 中文：变量 `document_version_id` 用于保存“文档版本标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Immutable document-version identifier.
    document_version_id: str
    # 中文：变量 `source_id` 用于保存“资料源标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Source identifier.
    source_id: str
    # 中文：变量 `title` 用于保存“标题”相关数据；其精确定义与约束见下方英文说明。
    # English: Best available display title.
    title: str
    # 中文：变量 `page_start` 用于保存“`page``start`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: First cited page.
    page_start: int | None
    # 中文：变量 `page_end` 用于保存“`page``end`”相关数据；其精确定义与约束见下方英文说明。
    # English: Last cited page.
    page_end: int | None
    # 中文：变量 `excerpt` 用于保存“`excerpt`”相关数据；其精确定义与约束见下方英文说明。
    # English: Short evidence excerpt.
    excerpt: str | None


class AnswerClaimSchema(APISchema):
    """中文：展示一条已经绑定 Need、Evidence 与 Citation 的可审计结论。

    English: Expose one auditable claim bound to needs, evidence, and citations.
    """

    id: str
    text: str
    need_ids: list[str]
    evidence_ids: list[str]
    citation_ids: list[str]
    verification_status: str


class AnswerItemSchema(APISchema):
    """中文：展示一个面向用户的回答项及其 Claim 标识。

    English: Expose one user-facing answer item and its claim identities.
    """

    id: str
    need_ids: list[str]
    text: str
    claim_ids: list[str]


class MissingInformationSchema(APISchema):
    """中文：披露部分回答中尚未得到充分证据支持的信息需要。

    English: Disclose an information need not sufficiently supported in a partial answer.
    """

    need_id: str
    description: str
    reason: str


class ChatRequest(APISchema):
    """中文：该类用于表示或实现“问答请求（ChatRequest）”的职责。

    English: Accept one natural-language question and optional authorized source restriction.
    """

    # 中文：变量 `query` 用于保存“查询”相关数据；其精确定义与约束见下方英文说明。
    # English: Natural-language enterprise knowledge question.
    query: str = Field(min_length=1, max_length=8000)
    # 中文：变量 `conversation_id` 用于保存“`conversation`标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Optional conversation label retained by clients.
    conversation_id: str | None = Field(default=None, max_length=128)
    # 中文：变量 `requested_source_ids` 用于保存“请求的资料源标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Requested source restriction intersected with trusted authorization.
    requested_source_ids: list[str] = Field(default_factory=list, max_length=100)


class ChatResponse(APISchema):
    """中文：该类用于表示或实现“问答响应（ChatResponse）”的职责。

    English: Expose either a verified answer or an intentional refusal.
    """

    # 中文：变量 `trace_id` 用于保存“追踪标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable request trace identifier.
    trace_id: str
    # 中文：变量 `status` 用于保存“状态”相关数据；其精确定义与约束见下方英文说明。
    # English: answered, partial, or refused.
    status: str
    # 中文：变量 `answer` 用于保存“答案”相关数据；其精确定义与约束见下方英文说明。
    # English: Verified answer text when answered.
    answer: str | None = None
    # 中文：变量 `citations` 用于保存“引用”相关数据；其精确定义与约束见下方英文说明。
    # English: Verified citations.
    citations: list[CitationSchema] = Field(default_factory=list)
    # 中文：结构化回答项用于 UI 分项展示，并保持旧 `answer` 字段兼容。
    # English: Structured items support itemized UI rendering while preserving `answer`.
    items: list[AnswerItemSchema] = Field(default_factory=list)
    # 中文：每条 Claim 必须已经通过引用验证并绑定证据。
    # English: Every exposed claim has passed citation verification and evidence binding.
    claims: list[AnswerClaimSchema] = Field(default_factory=list)
    # 中文：仅部分回答携带缺失信息，完整回答保持空列表。
    # English: Only partial answers carry missing information; complete answers keep it empty.
    missing_information: list[MissingInformationSchema] = Field(default_factory=list)
    # 中文：变量 `refusal_reason` 用于保存“拒答原因”相关数据；其精确定义与约束见下方英文说明。
    # English: Machine-readable refusal reason when refused.
    refusal_reason: str | None = None
    # 中文：变量 `message` 用于保存“消息”相关数据；其精确定义与约束见下方英文说明。
    # English: Safe user-facing refusal message.
    message: str | None = None
    # 中文：变量 `index_version_id` 用于保存“索引版本标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Immutable index snapshot used for retrieval.
    index_version_id: str | None = None
    # 中文：变量 `retrieval_rounds` 用于保存“检索`rounds`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Number of retrieval rounds.
    retrieval_rounds: int = 0


class IngestionAcceptedSchema(APISchema):
    """中文：该类用于表示或实现“资料接入已接受数据结构（IngestionAcceptedSchema）”的职责。

    English: Expose asynchronous document and job identifiers.
    """

    # 中文：变量 `document_id` 用于保存“文档标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Logical document identifier.
    document_id: str
    # 中文：变量 `document_version_id` 用于保存“文档版本标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Immutable document-version identifier.
    document_version_id: str
    # 中文：变量 `job_id` 用于保存“任务标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Durable ingestion job identifier.
    job_id: str
    # 中文：变量 `status` 用于保存“状态”相关数据；其精确定义与约束见下方英文说明。
    # English: Initial document state.
    status: str


class DeletionAcceptedSchema(APISchema):
    """中文：返回可轮询的异步删除任务标识。

    English: Return a pollable asynchronous deletion job identity.
    """

    deletion_job_id: str
    document_id: str
    status: str


class JobDetailSchema(APISchema):
    """中文：展示通用后台任务的安全状态投影。

    English: Expose a safe projection of any durable background job.
    """

    job_id: str
    job_type: str
    document_id: str
    document_version_id: str
    status: str
    attempt_count: int
    error_code: str | None = None
    error_message: str | None = None


class DocumentDetailSchema(APISchema):
    """中文：该类用于表示或实现“文档详情数据结构（DocumentDetailSchema）”的职责。

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
    # English: Current document lifecycle state.
    status: str
    # 中文：变量 `active_version_id` 用于保存“活动版本标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Active immutable version identifier.
    active_version_id: str | None
    # 中文：变量 `error_code` 用于保存“错误`code`”相关数据；其精确定义与约束见下方英文说明。
    # English: Safe ingestion failure code.
    error_code: str | None = None
    # 中文：活动版本创建时冻结的内容画像。
    # English: Content profile frozen when the active version was created.
    content_profile: str | None = None
    # 中文：活动版本实际使用的切块策略版本。
    # English: Exact chunk-strategy version used by the active version.
    chunk_strategy_version: str | None = None
    # 中文：质量门指标用于管理员验收和问题诊断。
    # English: Quality-gate metrics support administrator acceptance and diagnostics.
    quality_metrics: dict[str, object] = Field(default_factory=dict)


class SourceSchema(APISchema):
    """中文：该类用于表示或实现“资料源数据结构（SourceSchema）”的职责。

    English: Expose one source visible to the trusted caller.
    """

    # 中文：变量 `source_id` 用于保存“资料源标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable source identifier.
    source_id: str
    # 中文：变量 `name` 用于保存“`name`”相关数据；其精确定义与约束见下方英文说明。
    # English: Human-readable source name.
    name: str
    # 中文：变量 `description` 用于保存“`description`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Routing description.
    description: str
    # 中文：管理员声明的主要内容画像，决定文档结构与切块策略。
    # English: Administrator-declared content profile selecting structure/chunk strategy.
    content_profile: ContentProfile
    # 中文：可选高级策略覆盖；通常应保持为空。
    # English: Optional advanced strategy override; normally left empty.
    chunk_strategy_override: str | None = None
    # 中文：变量 `visibility` 用于保存“`visibility`”相关数据；其精确定义与约束见下方英文说明。
    # English: Public visibility label.
    visibility: str
    # 中文：画像修改后提示管理员对已有文档执行重新处理。
    # English: Profile changes require existing documents to be reprocessed.
    requires_reprocessing: bool = False


class SourceProfileUpdateSchema(APISchema):
    """中文：定义管理员更新资料源内容画像的请求结构。

    English: Define the administrator request for updating a source content profile.
    """

    # 中文：V4 允许六种受控画像，并由服务端注册表校验策略映射。
    # English: V4 accepts six controlled profiles validated by the server-side registry.
    content_profile: ContentProfile
    # 中文：受控策略覆盖用于高级调试和灰度验证。
    # English: Controlled override supports advanced diagnostics and staged validation.
    chunk_strategy_override: str | None = None


class IndexSchema(APISchema):
    """中文：该类用于表示或实现“索引数据结构（IndexSchema）”的职责。

    English: Expose one tenant index snapshot to administrators.
    """

    # 中文：变量 `index_version_id` 用于保存“索引版本标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Immutable index version identifier.
    index_version_id: str
    # 中文：变量 `status` 用于保存“状态”相关数据；其精确定义与约束见下方英文说明。
    # English: Publication state.
    status: str
    # 中文：变量 `chunk_count` 用于保存“文本块`count`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Number of represented chunks.
    chunk_count: int
    # 中文：变量 `config_fingerprint` 用于保存“配置指纹”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Reproducibility configuration fingerprint.
    config_fingerprint: str
    # 中文：变量 `created_at` 用于保存“`created``at`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Snapshot creation time.
    created_at: str
    # 中文：变量 `activated_at` 用于保存“`activated``at`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Snapshot activation time.
    activated_at: str | None


class IndexBuildResponse(APISchema):
    """中文：该类用于表示或实现“索引构建响应（IndexBuildResponse）”的职责。

    English: Expose a completed immutable index publication.
    """

    # 中文：变量 `index_version_id` 用于保存“索引版本标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: New immutable index version.
    index_version_id: str
    # 中文：变量 `chunk_count` 用于保存“文本块`count`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Number of represented chunks.
    chunk_count: int
    # 中文：变量 `activated` 用于保存“`activated`”相关数据；其精确定义与约束见下方英文说明。
    # English: Whether the new snapshot became active.
    activated: bool
    # 中文：变量 `previous_index_version_id` 用于保存“`previous`索引版本标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Prior active snapshot retained for rollback.
    previous_index_version_id: str | None


class TraceSchema(APISchema):
    """中文：该类用于表示或实现“追踪数据结构（TraceSchema）”的职责。

    English: Expose a redacted permission-aware trace view.
    """

    # 中文：变量 `trace_id` 用于保存“追踪标识符”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable trace identifier.
    trace_id: str
    # 中文：变量 `status` 用于保存“状态”相关数据；其精确定义与约束见下方英文说明。
    # English: Final workflow status.
    status: str
    # 中文：回答使用的不可变索引版本标识。
    # English: Immutable index version used by the answer.
    index_version_id: str | None
    # 中文：回答使用的查询快照标识。
    # English: Query snapshot identity used by the answer.
    snapshot_id: str | None
    # 中文：变量 `steps` 用于保存“`steps`”相关数据；其精确定义与约束见下方英文说明。
    # English: Ordered safe step mappings.
    steps: list[dict[str, object]]
    # 中文：变量 `metrics` 用于保存“指标”相关数据；其精确定义与约束见下方英文说明。
    # English: Safe aggregate measurements.
    metrics: dict[str, float | int | str]


class HealthSchema(APISchema):
    """中文：该类用于表示或实现“健康检查数据结构（HealthSchema）”的职责。

    English: Expose liveness or readiness state.
    """

    # 中文：变量 `status` 用于保存“状态”相关数据；其精确定义与约束见下方英文说明。
    # English: ok, ready, or unavailable.
    status: str
    # 中文：变量 `version` 用于保存“版本”相关数据；其精确定义与约束见下方英文说明。
    # English: Application version.
    version: str
