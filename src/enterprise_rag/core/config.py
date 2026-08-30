"""中文：本模块负责实现“配置”相关功能。

English: Load, merge, validate, and freeze the application's strongly typed settings.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from enterprise_rag.core.enums import AuthenticationMode, ErrorCategory
from enterprise_rag.core.exceptions import ValidationError, error_detail

# 中文：变量 `_ENV_PREFIX` 用于保存“`env``prefix`”相关数据；其精确定义与约束见下方英文说明。
# English: Environment variable prefix for nested settings overrides.
_ENV_PREFIX = "ENTERPRISE_RAG__"


class FrozenSettingsModel(BaseModel):
    """中文：该类用于表示或实现“冻结的设置模型（FrozenSettingsModel）”的职责。

    English: Provide immutable, strict behavior shared by all settings sections.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


class ApplicationSettings(FrozenSettingsModel):
    """中文：该类用于表示或实现“应用设置（ApplicationSettings）”的职责。

    English: Configure the application identity and execution environment.
    """

    # 中文：变量 `name` 用于保存“`name`”相关数据；其精确定义与约束见下方英文说明。
    # English: Stable product name used by logs, API metadata, and manifests.
    name: str = "enterprise-trusted-agentic-rag"
    # 中文：变量 `environment` 用于保存“`environment`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Runtime environment name such as production, development, or evaluation.
    environment: str = "production"
    # 中文：变量 `api_prefix` 用于保存“接口`prefix`”相关数据；其精确定义与约束见下方英文说明。
    # English: Public API version prefix.
    api_prefix: str = "/api/v1"
    # 中文：变量 `debug` 用于保存“`debug`”相关数据；其精确定义与约束见下方英文说明。
    # English: Enables verbose developer diagnostics without changing business behavior.
    debug: bool = False


class StorageSettings(FrozenSettingsModel):
    """中文：该类用于表示或实现“存储设置（StorageSettings）”的职责。

    English: Configure durable local paths and the SQL database connection.
    """

    # 中文：变量 `upload_dir` 用于保存“上传`dir`”相关数据；其精确定义与约束见下方英文说明。
    # English: Directory containing tenant-isolated original uploads.
    upload_dir: Path = Path("data/uploads")
    # 中文：变量 `index_dir` 用于保存“索引`dir`”相关数据；其精确定义与约束见下方英文说明。
    # English: Directory containing immutable index snapshots.
    index_dir: Path = Path("data/indexes")
    # 中文：变量 `trace_dir` 用于保存“追踪`dir`”相关数据；其精确定义与约束见下方英文说明。
    # English: Directory containing redacted trace files when file tracing is enabled.
    trace_dir: Path = Path("data/traces")
    # 中文：变量 `database_url` 用于保存“数据库`url`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: SQLAlchemy database URL used for durable metadata and jobs.
    database_url: str = "sqlite:///./data/database/enterprise_rag.db"


class IngestionSettings(FrozenSettingsModel):
    """中文：该类用于表示或实现“资料接入设置（IngestionSettings）”的职责。

    English: Configure upload validation and structure-aware chunk generation.
    """

    # 中文：变量 `allowed_extensions` 用于保存“`allowed``extensions`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Lowercase extensions accepted after MIME and content validation.
    allowed_extensions: tuple[str, ...] = ("pdf", "md", "txt")
    # 中文：变量 `max_file_size_mb` 用于保存“`max`文件`size``mb`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Maximum accepted original file size in mebibytes.
    max_file_size_mb: int = Field(default=50, ge=1, le=1024)
    # 中文：变量 `chunker_version` 用于保存“切块器版本”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Version string included in deterministic chunk and index identities.
    chunker_version: str = "structure-constrained-adaptive-v4"
    # 中文：变量 `min_chunk_tokens` 用于保存“`min`文本块词元”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Soft lower bound below which adjacent text units should be combined.
    min_chunk_tokens: int = Field(default=150, ge=1)
    # 中文：变量 `target_chunk_tokens` 用于保存“`target`文本块词元”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Preferred chunk size used during boundary scoring.
    target_chunk_tokens: int = Field(default=400, ge=1)
    # 中文：变量 `max_chunk_tokens` 用于保存“`max`文本块词元”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Hard chunk size above which a unit must be split.
    max_chunk_tokens: int = Field(default=700, ge=1)
    # 中文：变量 `semantic_boundary_threshold` 是向量相似度低于其时的候选切点中心值。
    # English: `semantic_boundary_threshold` centers the embedding-similarity split decision.
    semantic_boundary_threshold: float = Field(default=0.52, ge=-1.0, le=1.0)
    # 中文：变量 `semantic_ambiguity_margin` 定义交给 LLM 复核的模糊分数带宽。
    # English: `semantic_ambiguity_margin` defines the ambiguous band eligible for LLM review.
    semantic_ambiguity_margin: float = Field(default=0.08, ge=0.0, le=0.5)
    # 中文：以下五项是自适应边界总分中结构、语义、长度、标记和角色变化权重。
    # English: These five values weight structure, semantic gap, length, marker, and role change.
    boundary_structure_weight: float = Field(default=0.30, ge=0.0, le=1.0)
    boundary_semantic_weight: float = Field(default=0.30, ge=0.0, le=1.0)
    boundary_length_weight: float = Field(default=0.20, ge=0.0, le=1.0)
    boundary_marker_weight: float = Field(default=0.10, ge=0.0, le=1.0)
    boundary_role_weight: float = Field(default=0.10, ge=0.0, le=1.0)
    # 中文：基础边界阈值由长度压力动态上调或下调，硬边界不参与阈值判断。
    # English: Length pressure shifts this base threshold; hard boundaries bypass scoring.
    adaptive_boundary_threshold: float = Field(default=0.58, ge=0.0, le=1.0)
    # 中文：变量 `llm_boundary_enabled` 控制是否只在模糊边界调用 LLM。
    # English: `llm_boundary_enabled` controls LLM calls for ambiguous boundaries only.
    llm_boundary_enabled: bool = False
    # 中文：变量 `llm_boundary_max_calls` 限制单文档的 LLM 模糊边界复核次数。
    # English: `llm_boundary_max_calls` caps ambiguous LLM reviews per document.
    llm_boundary_max_calls: int = Field(default=8, ge=0, le=100)
    # 中文：变量 `parent_chunks_enabled` 控制是否建立叶子块到父上下文块的层级。
    # English: `parent_chunks_enabled` controls leaf-to-parent context hierarchy creation.
    parent_chunks_enabled: bool = True
    # 中文：变量 `job_lease_seconds` 用于保存“任务`lease``seconds`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Number of lease seconds before another worker may recover a running job.
    job_lease_seconds: int = Field(default=300, ge=30)
    # 中文：变量 `job_heartbeat_seconds` 控制 Worker 主动续租的固定间隔。
    # English: `job_heartbeat_seconds` controls the fixed worker lease-renewal interval.
    job_heartbeat_seconds: int = Field(default=60, ge=1)
    # 中文：变量 `max_request_body_size_mb` 限制 multipart 解析前的完整 HTTP 请求体。
    # English: `max_request_body_size_mb` limits the whole HTTP body before multipart parsing.
    max_request_body_size_mb: int = Field(default=55, ge=1, le=1024)

    @model_validator(mode="after")
    def validate_chunk_bounds(self) -> Self:
        """中文：该函数或方法负责“校验文本块边界”相关处理。

        English: Ensure minimum, target, and maximum chunk sizes are monotonic.
        """

        if not self.min_chunk_tokens <= self.target_chunk_tokens <= self.max_chunk_tokens:
            raise ValueError("chunk token bounds must satisfy min <= target <= max")
        if self.job_heartbeat_seconds * 2 >= self.job_lease_seconds:
            raise ValueError("job heartbeat must be less than half of the lease duration")
        if self.max_request_body_size_mb <= self.max_file_size_mb:
            raise ValueError(
                "request body limit must exceed the file limit to allow multipart overhead"
            )
        weight_sum = (
            self.boundary_structure_weight
            + self.boundary_semantic_weight
            + self.boundary_length_weight
            + self.boundary_marker_weight
            + self.boundary_role_weight
        )
        if abs(weight_sum - 1.0) > 1e-6:
            raise ValueError("adaptive boundary weights must sum to 1.0")
        return self


class EmbeddingSettings(FrozenSettingsModel):
    """中文：该类用于表示或实现“向量嵌入设置（EmbeddingSettings）”的职责。

    English: Configure interchangeable local or OpenAI-compatible embedding providers.
    """

    # 中文：变量 `provider` 用于保存“提供方”相关数据；其精确定义与约束见下方英文说明。
    # English: Provider kind selected by the infrastructure factory.
    provider: str = "local"
    # 中文：变量 `model` 用于保存“模型”相关数据；其精确定义与约束见下方英文说明。
    # English: Local model name or API model identifier.
    model: str = "BAAI/bge-small-zh-v1.5"
    # 中文：变量 `dimension` 用于保存“`dimension`”相关数据；其精确定义与约束见下方英文说明。
    # English: Expected embedding dimension; zero accepts the provider's reported dimension.
    dimension: int = Field(default=0, ge=0)
    # 中文：变量 `batch_size` 用于保存“批量`size`”相关数据；其精确定义与约束见下方英文说明。
    # English: Maximum number of texts sent in one provider call.
    batch_size: int = Field(default=32, ge=1, le=2048)
    # 中文：变量 `base_url` 用于保存“基础`url`”相关数据；其精确定义与约束见下方英文说明。
    # English: Optional OpenAI-compatible endpoint for remote embeddings.
    base_url: str | None = None
    # 中文：变量 `api_key_env` 用于保存“接口`key``env`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Name of the environment variable containing the API key.
    api_key_env: str = "EMBEDDING_API_KEY"


class OCRSettings(FrozenSettingsModel):
    """中文：配置扫描或混合 PDF 的可插拔逐页 OCR 能力。

    English: Configure pluggable page-level OCR for scanned or hybrid PDFs.
    """

    # 中文：变量 `enabled` 控制是否在缺少文本层时自动执行 OCR。
    # English: `enabled` controls automatic OCR when a page lacks a usable text layer.
    enabled: bool = False
    # 中文：变量 `provider` 选择当前基础设施适配器。
    # English: `provider` selects the active infrastructure adapter.
    provider: str = "tesseract"
    # 中文：变量 `language` 传递给本地 Tesseract 语言模型。
    # English: `language` is passed to the local Tesseract language model.
    language: str = "chi_sim+eng"
    # 中文：变量 `dpi` 控制 PDF 页面栅格化分辨率。
    # English: `dpi` controls PDF-page rasterization resolution.
    dpi: int = Field(default=250, ge=120, le=600)
    # 中文：变量 `minimum_confidence` 是自动发布 OCR 文本的最低平均置信度。
    # English: `minimum_confidence` is the lowest mean confidence allowed for auto-publication.
    minimum_confidence: float = Field(default=0.75, ge=0.0, le=1.0)


class RetrievalSettings(FrozenSettingsModel):
    """中文：该类用于表示或实现“检索设置（RetrievalSettings）”的职责。

    English: Configure hybrid retrieval, fusion, reranking, and evidence selection.
    """

    # 中文：变量 `dense_candidate_k` 用于保存“稠密向量检索候选项`k`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Dense candidates requested before permission-aware fusion.
    dense_candidate_k: int = Field(default=30, ge=1)
    # 中文：变量 `bm25_candidate_k` 用于保存“BM25 关键词检索候选项`k`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Lexical candidates requested before permission-aware fusion.
    bm25_candidate_k: int = Field(default=30, ge=1)
    # 中文：变量 `rrf_k` 用于保存“`rrf``k`”相关数据；其精确定义与约束见下方英文说明。
    # English: Rank constant used by Reciprocal Rank Fusion.
    rrf_k: int = Field(default=60, ge=1)
    # 中文：变量 `min_k` 用于保存“`min``k`”相关数据；其精确定义与约束见下方英文说明。
    # English: Minimum evidence count selected when sufficient candidates exist.
    min_k: int = Field(default=3, ge=1)
    # 中文：变量 `default_k` 用于保存“默认`k`”相关数据；其精确定义与约束见下方英文说明。
    # English: Fallback evidence count when no strong score discontinuity exists.
    default_k: int = Field(default=5, ge=1)
    # 中文：变量 `max_k` 用于保存“`max``k`”相关数据；其精确定义与约束见下方英文说明。
    # English: Hard upper bound for selected evidence.
    max_k: int = Field(default=10, ge=1)
    # 中文：变量 `reranker_enabled` 用于保存“重排器`enabled`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Whether a configured cross-encoder should be attempted.
    reranker_enabled: bool = True
    # 中文：变量 `reranker_model` 用于保存“重排器模型”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Local cross-encoder model attempted when reranking is enabled.
    reranker_model: str = "BAAI/bge-reranker-base"
    # 中文：变量 `context_token_budget` 用于保存“上下文词元预算”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Maximum token budget available to the final evidence context.
    context_token_budget: int = Field(default=6000, ge=256)
    # 中文：单个 Parent 最多消耗的上下文预算，防止大章节挤占全部证据。
    # English: Maximum tokens one expanded parent may consume from the evidence budget.
    max_parent_tokens: int = Field(default=1600, ge=128)
    # 中文：同一 Parent 下允许进入最终候选集的 Child 上限。
    # English: Maximum selected child hits that may originate from one parent.
    max_children_per_parent: int = Field(default=2, ge=1, le=20)
    # 中文：单一文档在最终证据包中的占比上限。
    # English: Maximum share of final evidence that one document may occupy.
    max_document_share: float = Field(default=0.6, gt=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_top_k_bounds(self) -> Self:
        """中文：该函数或方法负责“校验TopK 值边界”相关处理。

        English: Ensure dynamic Top-K bounds are monotonic.
        """

        if not self.min_k <= self.default_k <= self.max_k:
            raise ValueError("retrieval bounds must satisfy min_k <= default_k <= max_k")
        if self.max_parent_tokens > self.context_token_budget:
            raise ValueError("max_parent_tokens cannot exceed context_token_budget")
        return self


class AgentSettings(FrozenSettingsModel):
    """中文：该类用于表示或实现“智能体设置（AgentSettings）”的职责。

    English: Configure the bounded explicit Python agent state machine.
    """

    # 中文：变量 `max_retrieval_retries` 用于保存“`max`检索`retries`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Maximum number of rewrites after the initial retrieval attempt.
    max_retrieval_retries: int = Field(default=2, ge=0, le=5)
    # 中文：变量 `max_model_calls` 用于保存“`max`模型`calls`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Maximum provider calls across routing, grading, rewriting, and answering.
    max_model_calls: int = Field(default=8, ge=1)
    # 中文：变量 `max_total_tokens` 用于保存“`max``total`词元”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Maximum aggregate input and output token usage for one request.
    max_total_tokens: int = Field(default=24000, ge=512)
    # 中文：变量 `timeout_seconds` 用于保存“`timeout``seconds`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Wall-clock deadline for the complete question-answering workflow.
    timeout_seconds: int = Field(default=60, ge=1)


class LLMSettings(FrozenSettingsModel):
    """中文：该类用于表示或实现“大语言模型设置（LLMSettings）”的职责。

    English: Configure an OpenAI-compatible chat-completion provider.
    """

    # 中文：变量 `provider` 用于保存“提供方”相关数据；其精确定义与约束见下方英文说明。
    # English: Provider label retained in traces and evaluation fingerprints.
    provider: str = "openai-compatible"
    # 中文：变量 `model` 用于保存“模型”相关数据；其精确定义与约束见下方英文说明。
    # English: Chat model identifier sent to the configured endpoint.
    model: str = "gpt-4.1-mini"
    # 中文：变量 `base_url` 用于保存“基础`url`”相关数据；其精确定义与约束见下方英文说明。
    # English: Base URL for OpenAI-compatible chat completions.
    base_url: str = "http://localhost:11434/v1"
    # 中文：变量 `api_key_env` 用于保存“接口`key``env`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Name of the environment variable containing the provider API key.
    api_key_env: str = "LLM_API_KEY"
    # 中文：变量 `request_timeout_seconds` 用于保存“请求`timeout``seconds`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Per-request model timeout in seconds.
    request_timeout_seconds: int = Field(default=45, ge=1)
    # 中文：变量 `temperature` 用于保存“`temperature`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Sampling temperature used for evidence-grounded generation.
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)


class EvaluationSettings(FrozenSettingsModel):
    """中文：该类用于表示或实现“评估设置（EvaluationSettings）”的职责。

    English: Configure deterministic evaluation input, output, and random behavior.
    """

    # 中文：变量 `random_seed` 用于保存“`random``seed`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Fixed random seed recorded in every evaluation report.
    random_seed: int = 42
    # 中文：变量 `dataset_path` 用于保存“评估集`path`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Versioned JSONL or JSON evaluation dataset path.
    dataset_path: Path = Path("tests/fixtures/evaluation_dataset.json")
    # 中文：变量 `output_dir` 用于保存“输出`dir`”相关数据；其精确定义与约束见下方英文说明。
    # English: Directory receiving evaluation reports.
    output_dir: Path = Path("reports")


class SecuritySettings(FrozenSettingsModel):
    """中文：该类用于表示或实现“安全设置（SecuritySettings）”的职责。

    English: Configure tenancy, authorization, and development authentication safeguards.
    """

    # 中文：变量 `default_tenant_id` 用于保存“默认租户标识符”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Tenant used only by the explicitly enabled development identity provider.
    default_tenant_id: str = "demo-tenant"
    # 中文：认证模式必须唯一；生产配置只能选择 JWT 或可信代理。
    # English: Exactly one auth mode is active; production permits JWT or trusted proxy only.
    authentication_mode: AuthenticationMode = AuthenticationMode.TRUSTED_PROXY
    # 中文：变量 `enforce_access_scope` 用于保存“`enforce``access`范围”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Whether every online retrieval must receive a concrete access scope.
    enforce_access_scope: bool = True
    # 中文：变量 `demo_auth_enabled` 用于保存“`demo``auth``enabled`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Enables header-based demo identity construction outside production.
    demo_auth_enabled: bool = False
    # 中文：变量 `trusted_proxy_auth_enabled` 启用企业反向代理身份头适配器。
    # English: `trusted_proxy_auth_enabled` enables the enterprise reverse-proxy identity adapter.
    trusted_proxy_auth_enabled: bool = False
    # 中文：变量 `trusted_proxy_secret_env` 指定代理与应用共享密钥的环境变量名。
    # English: `trusted_proxy_secret_env` names the environment variable holding the proxy secret.
    trusted_proxy_secret_env: str = "ENTERPRISE_RAG_PROXY_SECRET"
    # 中文：JWT HMAC 密钥仅通过该环境变量读取，绝不写入配置文件或日志。
    # English: The JWT HMAC secret is read only from this environment variable.
    jwt_secret_env: str = "ENTERPRISE_RAG_JWT_SECRET"
    # 中文：验证令牌签发者，避免接受其他系统签发的相同格式令牌。
    # English: Validate token issuer to reject structurally similar tokens from other systems.
    jwt_issuer: str = "enterprise-rag"
    # 中文：验证令牌受众，限制凭证只能用于本 API。
    # English: Validate token audience so credentials are scoped to this API.
    jwt_audience: str = "enterprise-rag-api"
    # 中文：代理共享密钥头只证明请求来自受控网关，身份头仍会严格解析。
    # English: The proxy secret header proves gateway origin; identity headers remain validated.
    trusted_proxy_secret_header: str = "X-Enterprise-RAG-Proxy-Secret"


class Settings(FrozenSettingsModel):
    """中文：该类用于表示或实现“设置（Settings）”的职责。

    English: Aggregate every validated configuration section used by the application.
    """

    # 中文：变量 `config_version` 用于保存“配置版本”相关数据；其精确定义与约束见下方英文说明。
    # English: Schema version used to reject incompatible configuration files.
    config_version: str = "4.0"
    # 中文：变量 `application` 用于保存“应用”相关数据；其精确定义与约束见下方英文说明。
    # English: General application configuration.
    application: ApplicationSettings = ApplicationSettings()
    # 中文：变量 `storage` 用于保存“存储”相关数据；其精确定义与约束见下方英文说明。
    # English: Durable storage and database configuration.
    storage: StorageSettings = StorageSettings()
    # 中文：变量 `ingestion` 用于保存“资料接入”相关数据；其精确定义与约束见下方英文说明。
    # English: Document validation and chunking configuration.
    ingestion: IngestionSettings = IngestionSettings()
    # 中文：变量 `embedding` 用于保存“向量嵌入”相关数据；其精确定义与约束见下方英文说明。
    # English: Embedding provider configuration.
    embedding: EmbeddingSettings = EmbeddingSettings()
    # 中文：变量 `ocr` 配置扫描与混合 PDF 的逐页文本补齐。
    # English: `ocr` configures page-level text completion for scanned and hybrid PDFs.
    ocr: OCRSettings = OCRSettings()
    # 中文：变量 `retrieval` 用于保存“检索”相关数据；其精确定义与约束见下方英文说明。
    # English: Hybrid retrieval configuration.
    retrieval: RetrievalSettings = RetrievalSettings()
    # 中文：变量 `agent` 用于保存“智能体”相关数据；其精确定义与约束见下方英文说明。
    # English: Bounded agent execution configuration.
    agent: AgentSettings = AgentSettings()
    # 中文：变量 `llm` 用于保存“大语言模型”相关数据；其精确定义与约束见下方英文说明。
    # English: Language model provider configuration.
    llm: LLMSettings = LLMSettings()
    # 中文：变量 `evaluation` 用于保存“评估”相关数据；其精确定义与约束见下方英文说明。
    # English: Reproducible evaluation configuration.
    evaluation: EvaluationSettings = EvaluationSettings()
    # 中文：变量 `security` 用于保存“安全”相关数据；其精确定义与约束见下方英文说明。
    # English: Tenant and authentication safeguards.
    security: SecuritySettings = SecuritySettings()

    @model_validator(mode="after")
    def validate_authentication_mode(self) -> Self:
        """中文：校验互斥认证模式及旧配置开关，禁止生产环境信任客户端身份头。

        English: Validate exclusive auth mode and compatibility flags; never trust client headers.
        """

        is_production = self.application.environment == "production"
        if self.config_version != "4.0":
            raise ValueError("configuration schema version must be 4.0")
        if is_production and self.security.authentication_mode is AuthenticationMode.DEMO:
            raise ValueError("demo authentication mode is forbidden in production")
        if self.security.demo_auth_enabled != (
            self.security.authentication_mode is AuthenticationMode.DEMO
        ):
            raise ValueError("demo_auth_enabled must match authentication_mode=demo")
        if self.security.trusted_proxy_auth_enabled != (
            self.security.authentication_mode is AuthenticationMode.TRUSTED_PROXY
        ):
            raise ValueError(
                "trusted_proxy_auth_enabled must match authentication_mode=trusted_proxy"
            )
        return self


def load_settings(
    default_path: str | Path,
    override_path: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Settings:
    """中文：该函数或方法负责“加载设置”相关处理。

    English: Load default YAML, optional environment YAML, and nested environment overrides.
    """

    # 中文：变量 `resolved_default` 用于保存“`resolved`默认”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Default configuration path also establishes the project-relative base
    #   directory.
    resolved_default = Path(default_path).expanduser().resolve()
    # 中文：变量 `merged` 用于保存“`merged`”相关数据；其精确定义与约束见下方英文说明。
    # English: Lowest-precedence settings mapping loaded from the required default file.
    merged = _load_yaml_mapping(resolved_default)
    if override_path is not None:
        # 中文：变量 `override` 用于保存“`override`”相关数据；其精确定义与约束见下方英文说明。
        # English: Environment-specific values overlay only the keys they explicitly define.
        override = _load_yaml_mapping(Path(override_path).expanduser().resolve())
        # 中文：本步骤涉及文档、意图、默认，具体约束见下方英文说明。
        # English: ``extends`` documents human intent; the explicit default_path already
        #   resolves it.
        override.pop("extends", None)
        merged = _deep_merge(merged, override)
    # 中文：变量 `env_values` 用于保存“`env``values`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Process environment is copied so callers can inject a deterministic mapping
    #   in tests.
    env_values = dict(os.environ if environ is None else environ)
    merged = _deep_merge(merged, _environment_overrides(env_values))
    try:
        # 中文：变量 `settings` 用于保存“设置”相关数据；其精确定义与约束见下方英文说明。
        # English: Pydantic performs strict structural and cross-field validation.
        settings = Settings.model_validate(merged)
    except Exception as exc:
        raise ValidationError(
            error_detail(
                "INVALID_CONFIGURATION",
                ErrorCategory.VALIDATION,
                "Application configuration is invalid.",
                reason=str(exc),
            )
        ) from exc
    # 中文：变量 `project_root` 用于保存“`project``root`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: The project directory is the parent of the conventional configs directory.
    project_root = resolved_default.parent.parent
    return _resolve_storage_paths(settings, project_root)


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    """中文：该内部函数负责“加载YAML映射”相关处理。

    English: Read one YAML file and require a mapping at its root.
    """

    if not path.is_file():
        raise ValidationError(
            error_detail(
                "CONFIG_FILE_NOT_FOUND",
                ErrorCategory.VALIDATION,
                "A required configuration file does not exist.",
                path=str(path),
            )
        )
    # 中文：变量 `raw_value` 用于保存“`raw``value`”相关数据；其精确定义与约束见下方英文说明。
    # English: Parsed YAML value is untrusted configuration input.
    raw_value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw_value, dict):
        raise ValidationError(
            error_detail(
                "INVALID_CONFIG_ROOT",
                ErrorCategory.VALIDATION,
                "Configuration files must contain a mapping at the root.",
                path=str(path),
            )
        )
    return raw_value


def _deep_merge(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    """中文：该内部函数负责“深度合并”相关处理。

    English: Recursively merge mappings while replacing scalar and sequence values.
    """

    # 中文：变量 `merged` 用于保存“`merged`”相关数据；其精确定义与约束见下方英文说明。
    # English: Copy prevents configuration layers from mutating their caller's mapping.
    merged: dict[str, Any] = dict(base)
    for key, value in overlay.items():
        # 中文：变量 `existing` 用于保存“`existing`”相关数据；其精确定义与约束见下方英文说明。
        # English: Existing nested mappings are combined recursively.
        existing = merged.get(key)
        if isinstance(existing, Mapping) and isinstance(value, Mapping):
            merged[key] = _deep_merge(existing, value)
        else:
            merged[key] = value
    return merged


def _environment_overrides(environ: Mapping[str, str]) -> dict[str, Any]:
    """中文：该内部函数负责“环境覆盖项”相关处理。

    English: Convert ``ENTERPRISE_RAG__SECTION__FIELD`` variables into nested settings.
    """

    # 中文：变量 `result` 用于保存“结果”相关数据；其精确定义与约束见下方英文说明。
    # English: Result contains only recognized-prefix variables; Pydantic rejects unknown
    #   paths.
    result: dict[str, Any] = {}
    for name, raw_value in environ.items():
        if not name.startswith(_ENV_PREFIX):
            continue
        # 中文：变量 `path_parts` 用于保存“`path``parts`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Double underscores encode a path through nested settings objects.
        path_parts = [part.lower() for part in name[len(_ENV_PREFIX) :].split("__") if part]
        if not path_parts:
            continue
        # 中文：变量 `cursor` 用于保存“`cursor`”相关数据；其精确定义与约束见下方英文说明。
        # English: Cursor walks and creates the nested result mapping.
        cursor = result
        for part in path_parts[:-1]:
            cursor = cursor.setdefault(part, {})
        cursor[path_parts[-1]] = _parse_environment_value(raw_value)
    return result


def _parse_environment_value(raw_value: str) -> Any:
    """中文：该内部函数负责“解析环境值”相关处理。

    English: Parse JSON-compatible environment values while preserving ordinary strings.
    """

    try:
        # 中文：本注释说明当前代码步骤的用途、约束或设计原因。
        # English: JSON handles booleans, numbers, null, arrays, quoted strings, and
        #   objects.
        return json.loads(raw_value)
    except json.JSONDecodeError:
        return raw_value


def _resolve_storage_paths(settings: Settings, project_root: Path) -> Settings:
    """中文：该内部函数负责“解析存储`paths`”相关处理。

    English: Resolve relative local storage paths against the project root.
    """

    # 中文：变量 `resolved_storage` 用于保存“`resolved`存储”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Storage section is replaced immutably with absolute local directories.
    resolved_storage = settings.storage.model_copy(
        update={
            "upload_dir": _resolve_path(settings.storage.upload_dir, project_root),
            "index_dir": _resolve_path(settings.storage.index_dir, project_root),
            "trace_dir": _resolve_path(settings.storage.trace_dir, project_root),
        }
    )
    return settings.model_copy(update={"storage": resolved_storage})


def _resolve_path(value: Path, project_root: Path) -> Path:
    """中文：该内部函数负责“解析路径”相关处理。

    English: Resolve an absolute path directly or a relative path under the project root.
    """

    return value.resolve() if value.is_absolute() else (project_root / value).resolve()
