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
