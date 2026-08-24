"""中文：本模块负责实现“依赖”相关功能。

English: Build application dependencies and expose trusted request-scoped FastAPI providers.
"""

from __future__ import annotations

import json
import os
import secrets
import socket
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Annotated, cast

from dotenv import load_dotenv
from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session, sessionmaker

from enterprise_rag.agent.answer_generator import AnswerGenerator
from enterprise_rag.agent.citation_verifier import CitationVerifier
from enterprise_rag.agent.evidence_grader import EvidenceGrader
from enterprise_rag.agent.intent_router import IntentRouter
from enterprise_rag.agent.orchestrator import AgentOrchestrator
from enterprise_rag.agent.query_rewriter import QueryRewriter
from enterprise_rag.core.config import Settings, load_settings
from enterprise_rag.core.ids import content_sha256
from enterprise_rag.domain.models import Chunk, RetrievalScope, UserContext
from enterprise_rag.domain.protocols.models import EmbeddingProvider
from enterprise_rag.indexing.bm25_index import BM25IndexBuilder
from enterprise_rag.indexing.embedding_service import EmbeddingService
from enterprise_rag.indexing.index_coordinator import IndexCoordinator
from enterprise_rag.indexing.source_catalog import SourceCatalogBuilder
from enterprise_rag.indexing.vector_index import VectorIndexBuilder
from enterprise_rag.infrastructure.embeddings.api_provider import APIEmbeddingProvider
from enterprise_rag.infrastructure.embeddings.local_provider import LocalEmbeddingProvider
from enterprise_rag.infrastructure.indexes.index_runtime import LocalIndexRuntime
from enterprise_rag.infrastructure.llm.factory import create_llm
from enterprise_rag.infrastructure.ocr.tesseract_provider import TesseractOCRProvider
from enterprise_rag.infrastructure.persistence.database import (
    create_database_engine,
    create_session_factory,
    initialize_database,
    transactional_session,
)
from enterprise_rag.infrastructure.persistence.repositories import SQLAlchemyRepositories
from enterprise_rag.infrastructure.rerankers.cross_encoder import CrossEncoderReranker
from enterprise_rag.infrastructure.storage.local_file_store import LocalFileStore
from enterprise_rag.ingestion.boundary_analyzer import EmbeddingSimilarity, LLMBoundaryJudge
from enterprise_rag.ingestion.chunk_strategies import build_default_strategy_registry
from enterprise_rag.ingestion.cleaner import TextCleaner
from enterprise_rag.ingestion.loader_registry import LoaderRegistry
from enterprise_rag.ingestion.loaders.markdown_loader import MarkdownLoader
from enterprise_rag.ingestion.loaders.pdf_loader import PDFLoader
from enterprise_rag.ingestion.loaders.text_loader import TextLoader
from enterprise_rag.ingestion.metadata_extractor import MetadataExtractor
from enterprise_rag.ingestion.ocr import OCRProvider
from enterprise_rag.ingestion.pipeline import IngestionPipeline
from enterprise_rag.ingestion.quality_validator import ChunkQualityValidator
from enterprise_rag.ingestion.structure_parser import StructureParser
from enterprise_rag.ingestion.validator import UploadValidator
from enterprise_rag.observability.trace_recorder import JSONLTraceRecorder
from enterprise_rag.retrieval.bm25_retriever import BM25Retriever
from enterprise_rag.retrieval.context_builder import ContextBuilder
from enterprise_rag.retrieval.dense_retriever import DenseRetriever
from enterprise_rag.retrieval.dynamic_top_k import DynamicTopK
from enterprise_rag.retrieval.fusion import ReciprocalRankFusion
from enterprise_rag.retrieval.hybrid_retriever import HybridRetriever
from enterprise_rag.retrieval.query_normalizer import QueryNormalizer
from enterprise_rag.retrieval.reranker import CandidateReranker
from enterprise_rag.retrieval.source_profile_catalog import SourceProfileCatalog
from enterprise_rag.retrieval.source_router import SourceRouter
from enterprise_rag.services.chat_service import ChatService
from enterprise_rag.services.ingestion_service import IngestionService
from enterprise_rag.services.ingestion_worker import IngestionWorker
from enterprise_rag.services.knowledge_service import IndexBuildService, KnowledgeService
from enterprise_rag.services.trace_service import TraceService

# 中文：变量 `_PROJECT_ROOT` 用于保存“`project``root`”相关数据；
# 其精确定义与约束见下方英文说明。
# English: Conventional project root contains configs, data, scripts, and src.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True, slots=True)
class AppContainer:
    """中文：该类用于表示或实现“应用依赖容器（AppContainer）”的职责。

    English: Hold process-wide services constructed once by the FastAPI application factory.
    """

    # 中文：变量 `settings` 用于保存“设置”相关数据；其精确定义与约束见下方英文说明。
    # English: Fully validated immutable settings.
    settings: Settings
    # 中文：变量 `ingestion` 用于保存“资料接入”相关数据；其精确定义与约束见下方英文说明。
    # English: Document upload and durable job service.
    ingestion: IngestionService
    # 中文：变量 `knowledge` 用于保存“知识”相关数据；其精确定义与约束见下方英文说明。
    # English: Document/source/index lifecycle service.
    knowledge: KnowledgeService
    # 中文：变量 `chat` 用于保存“问答”相关数据；其精确定义与约束见下方英文说明。
    # English: Trusted question-answering service.
    chat: ChatService
    # 中文：变量 `traces` 用于保存“追踪”相关数据；其精确定义与约束见下方英文说明。
    # English: Permission-aware trace query service.
    traces: TraceService
    # 中文：变量 `indexes` 用于保存“索引”相关数据；其精确定义与约束见下方英文说明。
    # English: Index build service used by administrators and the worker.
    indexes: IndexBuildService
    # 中文：变量 `worker` 用于保存“工作进程”相关数据；其精确定义与约束见下方英文说明。
    # English: Durable single-iteration ingestion worker.
    worker: IngestionWorker
    # 中文：变量 `sessions` 用于保存“`sessions`”相关数据；其精确定义与约束见下方英文说明。
    # English: Shared SQLAlchemy session factory for scripts and health checks.
    sessions: sessionmaker[Session]


@lru_cache(maxsize=1)
def default_settings() -> Settings:
    """中文：该函数或方法负责“默认设置”相关处理。

    English: Load default plus optional environment-specific YAML settings once.
    """

    # 中文：本注释说明当前代码步骤的用途、约束或设计原因。
    # English: Environment selection may be provided by a simple process variable.
    import os

    # 中文：此处调用 `load_dotenv` 以执行“加载`dotenv`”相关步骤；具体约束见下方英文说明。
    # English: Local .env values are loaded without overriding explicit process
    #   environment variables.
    load_dotenv(_PROJECT_ROOT / ".env", override=False)
    environment = os.getenv("ENTERPRISE_RAG_ENV", "development")
    # 中文：变量 `override_path` 用于保存“`override``path`”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Only known environment files are selected automatically.
    override_path = _PROJECT_ROOT / "configs" / f"{environment}.yaml"
    return load_settings(
        _PROJECT_ROOT / "configs" / "default.yaml",
        override_path if override_path.is_file() else None,
    )


def build_container(settings: Settings | None = None) -> AppContainer:
    """中文：该函数或方法负责“构建依赖容器”相关处理。

    English: Construct concrete adapters and services from one immutable Settings object.
    """

    # 中文：变量 `configured` 用于保存“`configured`”相关数据；其精确定义与约束见下方英文说明。
    # English: Explicit settings support tests; cached defaults support process startup.
    configured = settings or default_settings()
    # 中文：变量 `engine` 用于保存“`engine`”相关数据；其精确定义与约束见下方英文说明。
    # English: Database engine and tables are initialized before repository-backed services.
    engine = create_database_engine(
        configured.storage.database_url,
        echo=configured.application.debug,
    )
    initialize_database(engine)
    sessions = create_session_factory(engine)
    # 中文：变量 `file_store` 用于保存“文件存储”相关数据；其精确定义与约束见下方英文说明。
    # English: Original file adapter owns tenant-isolated upload paths.
    file_store = LocalFileStore(configured.storage.upload_dir)
    # 中文：向量和 LLM 提供方先于接入流水线构建，使切块与在线检索共享模型语义空间。
    # English: Embedding and LLM providers are built before ingestion so chunking and online
    # retrieval share one semantic space.
    if configured.embedding.provider == "local":
        embedding_provider: EmbeddingProvider = LocalEmbeddingProvider(configured.embedding.model)
    elif configured.embedding.provider == "api":
        if configured.embedding.base_url is None:
            raise ValueError("API embedding provider requires base_url")
        embedding_provider = APIEmbeddingProvider(
            configured.embedding.model,
            configured.embedding.base_url,
            configured.embedding.api_key_env,
        )
    else:
        raise ValueError(f"unsupported embedding provider: {configured.embedding.provider}")
    embeddings = EmbeddingService(
        embedding_provider,
        configured.embedding.batch_size,
        configured.embedding.dimension,
    )
    llm = create_llm(configured.llm)
    # 中文：LLM 复核器只在配置开启且向量分数落入模糊区时被实际调用。
    # English: The LLM reviewer is called only when enabled and an embedding score is ambiguous.
    llm_boundary_judge = (
        LLMBoundaryJudge(llm) if configured.ingestion.llm_boundary_enabled else None
    )
    # 中文：关键变量 `ocr_provider` 统一承载可选 OCR 协议实现，避免具体适配器泄漏。
    # English: Key variable `ocr_provider` exposes only the optional OCR protocol.
    ocr_provider: OCRProvider | None
    if configured.ocr.enabled and configured.ocr.provider == "tesseract":
        ocr_provider = TesseractOCRProvider(configured.ocr.language, configured.ocr.dpi)
    elif configured.ocr.enabled:
        raise ValueError(f"unsupported OCR provider: {configured.ocr.provider}")
    else:
        ocr_provider = None
    # 中文：关键变量 `strategy_registry` 同时用于任务快照与 Worker 执行，避免解析不一致。
    # English: Key variable `strategy_registry` is shared by job snapshots and worker execution.
    strategy_registry = build_default_strategy_registry(
        configured.ingestion.min_chunk_tokens,
        configured.ingestion.target_chunk_tokens,
        configured.ingestion.max_chunk_tokens,
        similarity_provider=EmbeddingSimilarity(embedding_provider),
        llm_judge=llm_boundary_judge,
        semantic_threshold=configured.ingestion.semantic_boundary_threshold,
        ambiguity_margin=configured.ingestion.semantic_ambiguity_margin,
        create_parent_chunks=configured.ingestion.parent_chunks_enabled,
        max_llm_boundaries=configured.ingestion.llm_boundary_max_calls,
    )
    # 中文：关键变量 `effective_chunk_parameters` 同时写入版本快照和 Worker 校验器。
    # English: Key variable `effective_chunk_parameters` feeds both snapshots and worker checks.
    effective_chunk_parameters: dict[str, object] = {
        "min_tokens": configured.ingestion.min_chunk_tokens,
        "target_tokens": configured.ingestion.target_chunk_tokens,
        "max_tokens": configured.ingestion.max_chunk_tokens,
        "semantic_threshold": configured.ingestion.semantic_boundary_threshold,
        "ambiguity_margin": configured.ingestion.semantic_ambiguity_margin,
        "llm_boundary_enabled": configured.ingestion.llm_boundary_enabled,
        "llm_boundary_max_calls": configured.ingestion.llm_boundary_max_calls,
        "parent_chunks_enabled": configured.ingestion.parent_chunks_enabled,
    }
    # 中文：变量 `pipeline` 负责 PDF、Markdown 和 TXT 的统一接入准备。
    # English: `pipeline` prepares PDF, Markdown, and TXT through one ingestion path.
    pipeline = IngestionPipeline(
        loaders=LoaderRegistry(
            (
                PDFLoader(ocr_provider, configured.ocr.minimum_confidence),
                MarkdownLoader(),
                TextLoader(),
            )
        ),
        cleaner=TextCleaner(),
        structure_parser=StructureParser(),
        strategy_registry=strategy_registry,
        metadata_extractor=MetadataExtractor(),
        quality_validator=ChunkQualityValidator(),
        runtime_chunk_parameters=effective_chunk_parameters,
        runtime_embedding_fingerprint=embeddings.fingerprint,
        runtime_boundary_model_fingerprint=(
            llm_boundary_judge.fingerprint if llm_boundary_judge is not None else None
        ),
    )
    # 中文：变量 `coordinator` 用于保存“协调器”相关数据；其精确定义与约束见下方英文说明。
    # English: All index builders consume one shared plan through the coordinator.
    coordinator = IndexCoordinator(
        configured.storage.index_dir,
        embeddings,
        VectorIndexBuilder(),
        BM25IndexBuilder(),
        SourceCatalogBuilder(),
    )
    # 中文：变量 `config_fingerprint` 用于保存“配置指纹”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Settings fingerprint is stable, secret-free, and included in every snapshot.
    config_fingerprint = content_sha256(
        json.dumps(
            configured.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    index_service = IndexBuildService(
        sessions,
        coordinator,
        embeddings.fingerprint,
        configured.ingestion.chunker_version,
        config_fingerprint,
    )
    knowledge_service = KnowledgeService(
        sessions,
        index_service.rebuild_active,
        strategy_registry,
    )
    ingestion_service = IngestionService(
        sessions,
        UploadValidator(
            configured.ingestion.allowed_extensions,
            configured.ingestion.max_file_size_mb,
        ),
        file_store,
        strategy_registry=strategy_registry,
        chunk_parameters=effective_chunk_parameters,
        embedding_fingerprint=embeddings.fingerprint,
        boundary_model_fingerprint=(
            llm_boundary_judge.fingerprint if llm_boundary_judge is not None else None
        ),
    )

    # 中文：函数 `active_lookup` 用于执行“活动`lookup`”相关处理；
    # 其精确定义与约束见下方英文说明。
    # English: Database callback is the sole authority for active runtime version selection.
    def active_lookup(tenant_id: str) -> str:
        """中文：该函数或方法负责“活动查询”相关处理。

        English: Return the active tenant index ID or fail readiness explicitly.
        """

        with transactional_session(sessions) as session:
            active = SQLAlchemyRepositories(session).get_active_index(tenant_id)
            if active is None:
                raise RuntimeError("tenant has no active index")
            return active.id

    runtime = LocalIndexRuntime(configured.storage.index_dir, active_lookup)
    # 中文：变量 `reranker_provider` 用于保存“重排器提供方”相关数据；
    # 其精确定义与约束见下方英文说明。
    # English: Optional cross-encoder loads lazily and degrades to RRF if unavailable.
    reranker_provider = (
        CrossEncoderReranker(configured.retrieval.reranker_model)
        if configured.retrieval.reranker_enabled
        else None
    )

    # 中文：函数 `load_chunks` 用于执行“加载文本块”相关处理；其精确定义与约束见下方英文说明。
    # English: Tenant-scoped chunk callback creates a short independent read transaction.
    def load_chunks(tenant_id: str, chunk_ids: Sequence[str]) -> tuple[Chunk, ...]:
        """中文：该函数或方法负责“加载文本块”相关处理。

        English: Load only currently retrievable chunks for fused candidate IDs.
        """

        with transactional_session(sessions) as session:
            return tuple(
                SQLAlchemyRepositories(session).get_retrievable_chunks(tenant_id, chunk_ids)
            )

    def orchestrator_factory(scope: RetrievalScope) -> AgentOrchestrator:
        """中文：该函数或方法负责“编排器工厂”相关处理。

        English: Pin every retrieval component to the scope's immutable index version.
        """

        if scope.index_version_id is None:
            raise ValueError("orchestrator scope requires an index version")
        dense_index = runtime.dense(scope.tenant_id, scope.index_version_id)
        bm25_index = runtime.bm25(scope.tenant_id, scope.index_version_id)
        catalog = runtime.source_catalog(scope.tenant_id, scope.index_version_id)
        hybrid = HybridRetriever(
            QueryNormalizer(),
            SourceProfileCatalog(catalog),
            SourceRouter(),
            DenseRetriever(
                dense_index,
                embeddings,
                configured.retrieval.dense_candidate_k,
            ),
            BM25Retriever(bm25_index, configured.retrieval.bm25_candidate_k),
            ReciprocalRankFusion(configured.retrieval.rrf_k),
            CandidateReranker(reranker_provider),
            DynamicTopK(
                configured.retrieval.min_k,
                configured.retrieval.default_k,
                configured.retrieval.max_k,
                configured.retrieval.context_token_budget,
            ),
            ContextBuilder(),
            load_chunks,
        )
        return AgentOrchestrator(
            IntentRouter(),
            lambda query, round_number: hybrid.retrieve(query, scope, round_number),
            EvidenceGrader(),
            QueryRewriter(llm),
            AnswerGenerator(llm),
            CitationVerifier(),
            configured.agent.max_retrieval_retries,
            configured.agent.max_model_calls,
            configured.agent.max_total_tokens,
        )

    trace_recorder = JSONLTraceRecorder(configured.storage.trace_dir)
    chat_service = ChatService(
        sessions,
        orchestrator_factory,
        trace_recorder,
        configured.agent.timeout_seconds,
    )
    # 中文：关键变量 `worker_identity` 区分同机进程和容器，便于租约审计。
    # English: Key variable `worker_identity` distinguishes host processes and containers for
    # lease auditing.
    worker_identity = f"{socket.gethostname()}:{os.getpid()}"
    worker = IngestionWorker(
        sessions,
        file_store,
        pipeline,
        index_service.publish_ingested_version,
        worker_id=worker_identity,
        lease_seconds=configured.ingestion.job_lease_seconds,
        heartbeat_seconds=configured.ingestion.job_heartbeat_seconds,
    )
    return AppContainer(
        settings=configured,
        ingestion=ingestion_service,
        knowledge=knowledge_service,
        chat=chat_service,
        traces=TraceService(sessions, configured.storage.trace_dir),
        indexes=index_service,
        worker=worker,
        sessions=sessions,
    )


def get_container(request: Request) -> AppContainer:
    """中文：该函数或方法负责“获取依赖容器”相关处理。

    English: Return the process-wide container attached during application startup.
    """

    return cast(AppContainer, request.app.state.container)


def get_user_context(
    container: Annotated[AppContainer, Depends(get_container)],
    user_id: Annotated[str | None, Header(alias="X-User-ID")] = None,
    tenant_id: Annotated[str | None, Header(alias="X-Tenant-ID")] = None,
    roles: Annotated[str | None, Header(alias="X-Roles")] = None,
    source_ids: Annotated[str | None, Header(alias="X-Source-IDs")] = None,
    group_ids: Annotated[str | None, Header(alias="X-Group-IDs")] = None,
    proxy_secret: Annotated[str | None, Header(alias="X-Auth-Proxy-Secret")] = None,
) -> UserContext:
    """中文：该函数或方法负责“获取用户上下文”相关处理。

    English: Construct a trusted identity from explicit demo mode or a verified proxy adapter.
    """

    if container.settings.security.demo_auth_enabled:
        resolved_user_id = user_id or "demo-admin"
        resolved_tenant_id = tenant_id or container.settings.security.default_tenant_id
    elif container.settings.security.trusted_proxy_auth_enabled:
        # 中文：共享密钥只从环境读取并使用恒定时间比较，绝不写入日志或响应。
        # English: The shared secret comes only from the environment, is compared in constant
        # time, and is never logged or returned.
        expected_secret = os.getenv(container.settings.security.trusted_proxy_secret_env, "")
        if not expected_secret:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Trusted proxy authentication is not fully configured.",
            )
        if proxy_secret is None or not secrets.compare_digest(proxy_secret, expected_secret):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Trusted proxy authentication failed.",
            )
        if not user_id or not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Trusted proxy identity headers are incomplete.",
            )
        resolved_user_id = user_id
        resolved_tenant_id = tenant_id
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A production identity provider is required.",
        )
    # 中文：只有显式 Demo 模式提供管理员缺省值；生产代理必须明确传递角色。
    # English: Only explicit demo mode defaults to admin; production proxies must send roles.
    default_roles = "admin" if container.settings.security.demo_auth_enabled else ""
    resolved_roles = frozenset(_csv(roles or default_roles))
    return UserContext(
        user_id=resolved_user_id,
        tenant_id=resolved_tenant_id,
        roles=resolved_roles,
        allowed_source_ids=frozenset(_csv(source_ids or "")),
        group_ids=frozenset(_csv(group_ids or "")),
    )


def _csv(value: str) -> tuple[str, ...]:
    """中文：该内部函数负责“CSV”相关处理。

    English: Parse a comma-separated header into stripped non-empty values.
    """

    return tuple(item.strip() for item in value.split(",") if item.strip())
