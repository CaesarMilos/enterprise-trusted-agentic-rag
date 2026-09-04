"""中文：本模块负责实现“`enums`”相关功能。

English: Define shared, serializable business enumerations used throughout the application.
"""

from __future__ import annotations

from enum import StrEnum


class DocumentStatus(StrEnum):
    """中文：该类用于表示或实现“文档状态（DocumentStatus）”的职责。

    English: Describe the lifecycle state of a logical document.
    """

    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    # 中文：扫描型或混合型 PDF 缺少足够文本层，需要 OCR 后才能继续。
    # English: A scanned or hybrid PDF needs OCR before ingestion can continue.
    NEEDS_OCR = "needs_ocr"
    # 中文：文本可提取但结构或质量存在风险，需要管理员复核。
    # English: Extracted content has structural or quality risks requiring review.
    NEEDS_REVIEW = "needs_review"
    # 中文：文件损坏、加密或明确超出当前接入能力。
    # English: The document is damaged, encrypted, or explicitly unsupported.
    UNSUPPORTED = "unsupported"
    FAILED = "failed"
    PENDING_DELETE = "pending_delete"
    DELETED = "deleted"


class JobStatus(StrEnum):
    """中文：该类用于表示或实现“任务状态（JobStatus）”的职责。

    English: Describe the durable execution state of an ingestion job.
    """

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    # 中文：任务因缺少 OCR 能力而安全暂停，不视为程序故障。
    # English: The job paused safely because OCR is required, not because code failed.
    NEEDS_OCR = "needs_ocr"
    # 中文：任务输出需要管理员人工复核后才能入索引。
    # English: The job output requires administrator review before indexing.
    NEEDS_REVIEW = "needs_review"
    # 中文：文件类型或状态明确不受当前版本支持。
    # English: The input is explicitly unsupported by the current version.
    UNSUPPORTED = "unsupported"
    FAILED = "failed"
    # 中文：任务在发布前响应删除或管理员请求而终止，不能继续写入文档或索引。
    # English: The job stopped before publication after deletion or an administrator request.
    CANCELLED = "cancelled"
    # 中文：任务持有的文档 generation 已失效；这是可解释终态而非普通失败。
    # English: The document generation was invalidated; this is an explainable terminal state.
    STALE = "stale"


class IndexStatus(StrEnum):
    """中文：该类用于表示或实现“索引状态（IndexStatus）”的职责。

    English: Describe the publication state of an immutable index snapshot.
    """

    STAGING = "staging"
    READY = "ready"
    ACTIVE = "active"
    RETIRED = "retired"
    FAILED = "failed"
    # 中文：候选索引因生命周期 fencing 或显式取消而停止发布。
    # English: A candidate publication stopped because of lifecycle fencing or cancellation.
    CANCELLED = "cancelled"
    # 中文：失败或取消的索引制品已完成物理回收，仅保留审计记录。
    # English: Failed or cancelled artifacts were physically removed while audit data remains.
    PURGED = "purged"


class AgentStatus(StrEnum):
    """中文：该类用于表示或实现“智能体状态（AgentStatus）”的职责。

    English: Describe the terminal or intermediate state of one agent execution.
    """

    CREATED = "created"
    RETRIEVING = "retrieving"
    GRADING = "grading"
    REWRITING = "rewriting"
    GENERATING = "generating"
    VERIFYING = "verifying"
    ANSWERED = "answered"
    # 中文：至少一个必需信息需要已回答，其余缺口被显式披露。
    # English: At least one required need was answered and the remaining gaps were disclosed.
    PARTIAL = "partial"
    REFUSED = "refused"
    UNSUPPORTED = "unsupported"
    ERROR = "error"
    TIMEOUT = "timeout"


class IntentType(StrEnum):
    """中文：该类用于表示或实现“意图类型（IntentType）”的职责。

    English: Classify a request before the knowledge retrieval workflow runs.
    """

    KNOWLEDGE = "knowledge"
    SMALL_TALK = "small_talk"
    CAPABILITY = "capability"
    UNSUPPORTED = "unsupported"
    UNSAFE = "unsafe"


class ErrorCategory(StrEnum):
    """中文：该类用于表示或实现“错误`category`（ErrorCategory）”的职责。

    English: Group stable error codes into operationally meaningful categories.
    """

    VALIDATION = "validation"
    NOT_FOUND = "not_found"
    PERMISSION = "permission"
    CONFLICT = "conflict"
    STORAGE = "storage"
    PARSING = "parsing"
    INDEX = "index"
    RETRIEVAL = "retrieval"
    MODEL = "model"
    TIMEOUT = "timeout"
    INTERNAL = "internal"


class RefusalReason(StrEnum):
    """中文：该类用于表示或实现“拒答原因（RefusalReason）”的职责。

    English: Describe why the system intentionally did not produce an answer.
    """

    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    UNSUPPORTED_REQUEST = "unsupported_request"
    UNSAFE_REQUEST = "unsafe_request"
    ACCESS_DENIED = "access_denied"
    EVIDENCE_CONFIDENCE_LOW = "evidence_confidence_low"
    DOCUMENT_PROCESSING = "document_processing"
    DOCUMENT_NEEDS_OCR = "document_needs_ocr"
    DEADLINE_EXCEEDED = "deadline_exceeded"


class SourceVisibility(StrEnum):
    """中文：该类用于表示或实现“资料源可见性（SourceVisibility）”的职责。

    English: Describe which audience may retrieve a knowledge source.
    """

    PRIVATE = "private"
    TENANT = "tenant"
    RESTRICTED = "restricted"


class ContentProfile(StrEnum):
    """中文：定义资料源级内容画像，用于确定结构识别与切块策略。

    English: Define source-level content profiles that select structure and chunking rules.
    """

    # 中文：普通连续文本使用通用结构与长度规则。
    # English: General continuous prose uses the generic deterministic strategy.
    GENERAL_PROSE = "general_prose"
    # 中文：说明书、操作手册、维修手册和故障排查资料。
    # English: Manuals, operating guides, maintenance guides, and troubleshooting content.
    MANUAL = "manual"
    # 中文：API、配置、运维、开发和技术规范类文档。
    # English: API, configuration, operations, development, and specification documents.
    TECHNICAL_DOC = "technical_doc"
    # 中文：法规、制度、合同和政策文本，以编章节条款项作为强结构边界。
    # English: Regulations, policies, and contracts use article and clause boundaries.
    REGULATION = "regulation"
    # 中文：论文、研究报告和白皮书按摘要、章节、方法与结论组织。
    # English: Papers and reports are organized by abstract, sections, methods, and conclusions.
    ACADEMIC = "academic"
    # 中文：叙事材料以章节、场景和自然段作为主要边界。
    # English: Narrative material uses chapters, scenes, and paragraphs as primary boundaries.
    NARRATIVE = "narrative"


class AuthenticationMode(StrEnum):
    """中文：定义互斥认证模式，禁止生产环境混用可信与不可信身份来源。

    English: Define mutually exclusive authentication modes and identity trust boundaries.
    """

    DEMO = "demo"
    JWT = "jwt"
    TRUSTED_PROXY = "trusted_proxy"


class DocumentLifecycleStatus(StrEnum):
    """中文：描述逻辑文档独立于处理任务和版本质量的生命周期。

    English: Describe a logical document lifecycle independently of jobs and version quality.
    """

    ACTIVE = "active"
    PENDING_DELETE = "pending_delete"
    DELETED = "deleted"


class DocumentVersionStatus(StrEnum):
    """中文：描述不可变文档版本的候选、发布和退役状态。

    English: Describe candidate, publication, and retirement states of immutable versions.
    """

    CANDIDATE = "candidate"
    PUBLISHED = "published"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class JobExecutionStatus(StrEnum):
    """中文：描述与业务质量结论分离的持久任务执行状态。

    English: Describe durable job execution states separated from business quality decisions.
    """

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    STALE = "stale"
    DEAD_LETTER = "dead_letter"


class JobType(StrEnum):
    """中文：区分共享同一可靠任务框架的后台任务类型。

    English: Distinguish background job kinds sharing the durable job framework.
    """

    INGESTION = "ingestion"
    DELETION = "deletion"
    INDEX_REBUILD = "index_rebuild"
    RECOVERY = "recovery"


class QualityDecision(StrEnum):
    """中文：描述摄取产物质量，而不是任务是否成功运行。

    English: Describe ingestion artifact quality rather than job execution success.
    """

    PASS = "pass"
    PASS_WITH_WARNINGS = "pass_with_warnings"
    NEEDS_REVIEW = "needs_review"
    FAIL = "fail"


class DocumentOperationalStatus(StrEnum):
    """中文：提供由多套状态派生的权限安全 UI 展示状态。

    English: Provide a permission-safe UI status derived from independent state machines.
    """

    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    READY_WITH_WARNINGS = "ready_with_warnings"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"
    PENDING_DELETE = "pending_delete"
    DELETED = "deleted"


class LeaseCheckResult(StrEnum):
    """中文：精确区分取消、租约所有权丢失、过期和 generation 失效。

    English: Distinguish cancellation, ownership loss, expiry, and stale document generation.
    """

    VALID = "valid"
    CANCEL_REQUESTED = "cancel_requested"
    LEASE_OWNERSHIP_LOST = "lease_ownership_lost"
    LEASE_EXPIRED = "lease_expired"
    DOCUMENT_GENERATION_STALE = "document_generation_stale"


class CanonicalContentProfile(StrEnum):
    """中文：定义跨法规、说明书和流程文档复用的通用结构画像。

    English: Define reusable structural profiles across rules, manuals, and procedures.
    """

    NUMBERED_RULE_DOCUMENT = "numbered_rule_document"
    SECTIONED_TECHNICAL_MANUAL = "sectioned_technical_manual"
    PROCEDURE_GUIDE = "procedure_guide"
    GENERAL_EXPOSITORY = "general_expository"


class ProfileMode(StrEnum):
    """中文：说明资料源画像由管理员显式配置还是自动解析。

    English: State whether a source profile is explicitly configured or automatically resolved.
    """

    EXPLICIT = "explicit"
    AUTOMATIC = "automatic"


class ProfileMethod(StrEnum):
    """中文：记录文档版本最终画像的可审计解析方法。

    English: Record the auditable method used to resolve a version's final profile.
    """

    SOURCE_EXPLICIT = "source_explicit"
    CONTENT_PROFILER = "content_profiler"
    INHERITED = "inherited"
    FALLBACK = "fallback"


class ContractEnforcementMode(StrEnum):
    """中文：定义内容契约不匹配时的处置强度。

    English: Define enforcement strength when content conflicts with a source contract.
    """

    WARN = "warn"
    REVIEW = "review"
    REJECT = "reject"


class AuthorityPolicyMode(StrEnum):
    """中文：限定允许系统使用的文档权威顺序策略。

    English: Restrict authority-ordering policies the system may apply.
    """

    NONE = "none"
    EXPLICIT_PRIORITY = "explicit_priority"


class StructureType(StrEnum):
    """中文：定义与具体文档名称无关的通用业务结构类型。

    English: Define generic business structures independent of specific document names.
    """

    HEADING = "heading"
    NUMBERED_CLAUSE = "numbered_clause"
    DEFINITION = "definition"
    GENERAL_PARAGRAPH = "general_paragraph"
    PROCEDURE_STEP = "procedure_step"
    PREREQUISITE = "prerequisite"
    WARNING = "warning"
    PARAMETER_TABLE = "parameter_table"
    TROUBLESHOOTING_ENTRY = "troubleshooting_entry"
    EXCEPTION = "exception"
    APPENDIX = "appendix"


class NeedNecessity(StrEnum):
    """中文：说明信息需要是否决定回答完整性。

    English: State whether an information need determines answer completeness.
    """

    REQUIRED = "required"
    OPTIONAL = "optional"


class NeedOrigin(StrEnum):
    """中文：记录信息需要来自用户、问题拆解还是证据发现。

    English: Record whether a need came from the user, decomposition, or discovered evidence.
    """

    USER_EXPLICIT = "user_explicit"
    QUERY_DECOMPOSED = "query_decomposed"
    EVIDENCE_DISCOVERED = "evidence_discovered"


class InformationNeedIntent(StrEnum):
    """中文：定义跨文档类型通用的信息需求意图。

    English: Define document-agnostic information-need intents.
    """

    FACT = "fact"
    DEFINITION = "definition"
    RULE = "rule"
    CONDITION = "condition"
    EXCEPTION = "exception"
    PROCEDURE = "procedure"
    PARAMETER = "parameter"
    TROUBLESHOOTING = "troubleshooting"
    COMPARISON = "comparison"
    SUMMARY = "summary"
    UNKNOWN = "unknown"


class AnchorType(StrEnum):
    """中文：定义查询改写和检索过程中不可丢失的精确锚点类型。

    English: Define exact anchor kinds that retrieval and rewriting must preserve.
    """

    DOCUMENT_NAME = "document_name"
    STRUCTURE_ID = "structure_id"
    MODEL_NUMBER = "model_number"
    ERROR_CODE = "error_code"
    VERSION = "version"
    DATE = "date"
    PERSON = "person"
    ORGANIZATION = "organization"
    NUMERIC_VALUE = "numeric_value"


class AnswerFormat(StrEnum):
    """中文：定义用户请求的展示格式，不参与知识覆盖判断。

    English: Define requested presentation formats excluded from knowledge coverage grading.
    """

    AUTO = "auto"
    PARAGRAPH = "paragraph"
    LIST = "list"
    TABLE = "table"
    STEPS = "steps"


class EvidenceStatus(StrEnum):
    """中文：描述单个信息需要的证据状态。

    English: Describe the evidence status of one information need.
    """

    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"
    CONFLICTING = "conflicting"
    AMBIGUOUS = "ambiguous"


class EvidenceCoverageDecision(StrEnum):
    """中文：描述所有必需信息需要聚合后的证据决策。

    English: Describe the aggregate evidence decision across required needs.
    """

    COMPLETE = "complete"
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"
    CONFLICTING = "conflicting"
    AMBIGUOUS = "ambiguous"


class ClaimModality(StrEnum):
    """中文：定义证据命题的事实或规范模态。

    English: Define factual and normative modalities of evidence propositions.
    """

    FACT = "fact"
    PERMITTED = "permitted"
    REQUIRED = "required"
    PROHIBITED = "prohibited"
    CONDITIONAL = "conditional"
    EXCEPTION = "exception"


class PropositionRelationship(StrEnum):
    """中文：定义两条证据命题之间受约束的关系类型。

    English: Define constrained relationships between two evidence propositions.
    """

    CONFLICT = "conflict"
    COMPATIBLE = "compatible"
    EXCEPTION = "exception"
    DIFFERENT_SCOPE = "different_scope"
    AMBIGUOUS = "ambiguous"


class ClaimVerificationStatus(StrEnum):
    """中文：描述答案 Claim 是否得到证据验证。

    English: Describe whether an answer claim passed evidence verification.
    """

    VERIFIED = "verified"
    UNSUPPORTED = "unsupported"
    CONFLICTING = "conflicting"
    AMBIGUOUS = "ambiguous"


class AnswerStatus(StrEnum):
    """中文：定义 V5 结构化回答的最终状态。

    English: Define terminal states of the V5 structured answer protocol.
    """

    ANSWERED = "answered"
    PARTIAL = "partial"
    REFUSED = "refused"
    CONFLICTING = "conflicting"


class SnapshotStatus(StrEnum):
    """中文：描述查询知识快照的租约状态。

    English: Describe the lease state of a query knowledge snapshot.
    """

    ACTIVE = "active"
    CLOSED = "closed"
    EXPIRED = "expired"
    REVOKED = "revoked"


class RevocationScopeType(StrEnum):
    """中文：定义即时撤销可以作用的知识对象范围。

    English: Define knowledge scopes subject to immediate revocation.
    """

    SOURCE = "source"
    DOCUMENT = "document"
    DOCUMENT_VERSION = "document_version"


class TraceLevel(StrEnum):
    """中文：定义追踪数据的详细程度和保留策略。

    English: Define trace detail levels and their retention policies.
    """

    SUMMARY = "summary"
    DIAGNOSTIC = "diagnostic"
    EVALUATION = "evaluation"


class StateActor(StrEnum):
    """中文：定义获准改变各状态机的可信组件身份。

    English: Define trusted components authorized to mutate state machines.
    """

    INGESTION_SERVICE = "ingestion_service"
    INGESTION_WORKER = "ingestion_worker"
    PUBLICATION_SERVICE = "publication_service"
    DELETION_SERVICE = "deletion_service"
    DELETION_WORKER = "deletion_worker"
    RECOVERY_SERVICE = "recovery_service"
    SNAPSHOT_SERVICE = "snapshot_service"
    INDEX_CLEANER = "index_cleaner"
    MIGRATION = "migration"
