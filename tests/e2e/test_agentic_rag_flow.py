"""中文：使用真实 SQLite、FAISS、API 和 Worker 验证完整可信问答链路。

English: Verify the complete trusted question-answering path with real SQLite, FAISS, API,
and worker components.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from enterprise_rag.api import dependencies as dependency_module
from enterprise_rag.api.application import create_app
from enterprise_rag.core.config import (
    AgentSettings,
    ApplicationSettings,
    EmbeddingSettings,
    IngestionSettings,
    RetrievalSettings,
    SecuritySettings,
    Settings,
    StorageSettings,
)
from enterprise_rag.core.enums import AuthenticationMode, ContentProfile, SourceVisibility
from enterprise_rag.domain.models import Source
from enterprise_rag.domain.protocols.models import ModelResponse, ModelUsage
from enterprise_rag.infrastructure.persistence.database import transactional_session
from enterprise_rag.infrastructure.persistence.orm_models import TenantRow
from enterprise_rag.infrastructure.persistence.repositories import SQLAlchemyRepositories

# 中文：缺少本地 FAISS 二进制时跳过本验收测试，而不是退化成伪索引。
# English: Skip this acceptance test when the real local FAISS binary is unavailable rather
# than replacing the index with a fake.
pytest.importorskip("faiss", reason="the real FAISS runtime is required for this E2E test")


class DeterministicEmbeddingProvider:
    """中文：为端到端测试提供不联网、非零且可复现的固定维度向量。

    English: Provide offline, non-zero, reproducible fixed-dimension vectors for the E2E test.
    """

    def __init__(self, model_name: str, device: str | None = None) -> None:
        """中文：保存测试模型名；设备参数仅用于兼容生产工厂签名。

        English: Store the test model name; the device argument only matches the production
        factory signature.
        """

        # 中文：关键变量 `_model_name` 进入索引指纹并保证验收结果可审计。
        # English: Key variable `_model_name` enters the index fingerprint for auditable tests.
        self._model_name = model_name
        self._device = device

    @property
    def fingerprint(self) -> str:
        """中文：返回稳定的测试向量提供方指纹。

        English: Return the stable test embedding-provider fingerprint.
        """

        return f"deterministic-test:{self._model_name}:16"

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """中文：把字符散列到十六维向量并保留输入顺序。

        English: Hash characters into sixteen-dimensional vectors while preserving order.
        """

        vectors: list[list[float]] = []
        for text in texts:
            # 中文：关键变量 `vector` 的最后一维恒为一，避免空白输入产生零范数。
            # English: Key variable `vector` keeps its final component at one so even blank
            # input cannot produce a zero norm.
            vector = [0.0] * 16
            vector[-1] = 1.0
            for position, character in enumerate(text):
                vector[(ord(character) + position) % 15] += 1.0
            vectors.append(vector)
        return vectors


class DeterministicAnswerModel:
    """中文：只为最终答案生成返回一条可被确定性引用验证器核验的回答。

    English: Return one answer that the deterministic citation verifier can validate.
    """

    @property
    def fingerprint(self) -> str:
        """中文：返回稳定的测试语言模型指纹。

        English: Return the stable test language-model fingerprint.
        """

        return "deterministic-answer-model:v1"

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        metadata: Mapping[str, str] | None = None,
    ) -> ModelResponse:
        """中文：根据操作类型返回有引用的答案或安全查询改写。

        English: Return a cited answer or safe query rewrite according to the operation type.
        """

        del system_prompt, user_prompt
        # 中文：关键变量 `operation` 让同一测试适配器覆盖答案和潜在改写调用。
        # English: Key variable `operation` lets one test adapter cover answer and optional
        # rewrite calls.
        operation = (metadata or {}).get("operation", "")
        text = (
            "设备维护前必须断开电源[C1]。"
            if operation == "answer_generation"
            else "设备维护前必须断开电源"
        )
        return ModelResponse(
            text=text,
            usage=ModelUsage(input_tokens=8, output_tokens=8),
            model="deterministic-answer-model",
        )


def _settings(tmp_path: Path) -> Settings:
    """中文：构造全部数据都位于 pytest 临时目录的隔离设置。

    English: Build isolated settings whose durable artifacts all live under pytest's temp path.
    """

    return Settings(
        application=ApplicationSettings(environment="development"),
        storage=StorageSettings(
            upload_dir=tmp_path / "uploads",
            index_dir=tmp_path / "indexes",
            trace_dir=tmp_path / "traces",
            database_url=f"sqlite:///{tmp_path / 'enterprise-rag.db'}",
        ),
        ingestion=IngestionSettings(
            max_file_size_mb=1,
            max_request_body_size_mb=2,
            min_chunk_tokens=1,
            target_chunk_tokens=80,
            max_chunk_tokens=160,
            llm_boundary_enabled=False,
            parent_chunks_enabled=False,
            job_lease_seconds=60,
            job_heartbeat_seconds=10,
        ),
        embedding=EmbeddingSettings(
            provider="local",
            model="deterministic-e2e",
            dimension=16,
            batch_size=8,
        ),
        retrieval=RetrievalSettings(
            dense_candidate_k=3,
            bm25_candidate_k=3,
            min_k=1,
            default_k=1,
            max_k=3,
            reranker_enabled=False,
            context_token_budget=512,
            max_parent_tokens=256,
        ),
        agent=AgentSettings(
            max_retrieval_retries=0,
            max_model_calls=2,
            max_total_tokens=2048,
            timeout_seconds=30,
        ),
        security=SecuritySettings(
            default_tenant_id="e2e-tenant",
            authentication_mode=AuthenticationMode.DEMO,
            demo_auth_enabled=True,
        ),
    )


def test_upload_worker_faiss_and_chat_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """中文：验证上传、持久任务、切块、真实索引、检索、回答与引用形成闭环。

    English: Verify upload, durable job, chunking, real indexing, retrieval, answer, and
    citation as one closed loop.
    """

    # 中文：生产依赖工厂仍被完整使用，只替换会联网或下载模型的两个边界适配器。
    # English: The production dependency factory remains intact; only the two network/model
    # download boundary adapters are replaced.
    monkeypatch.setattr(
        dependency_module,
        "LocalEmbeddingProvider",
        DeterministicEmbeddingProvider,
    )
    monkeypatch.setattr(
        dependency_module,
        "create_llm",
        lambda _: DeterministicAnswerModel(),
    )
    container = dependency_module.build_container(_settings(tmp_path))

    # 中文：租户和资料源通过真实 SQLAlchemy 仓储写入同一个临时 SQLite 数据库。
    # English: The tenant and source enter the same temporary SQLite database through the real
    # SQLAlchemy repository.
    with transactional_session(container.sessions) as session:
        session.add(TenantRow(id="e2e-tenant", name="E2E Tenant", is_active=True))
        session.flush()
        SQLAlchemyRepositories(session).add_source(
            Source(
                id="manual-source",
                tenant_id="e2e-tenant",
                name="设备维护说明书",
                description="设备维护、断电和安全操作说明",
                content_profile=ContentProfile.MANUAL,
                visibility=SourceVisibility.TENANT,
            )
        )

    application = create_app(container)
    with TestClient(application) as client:
        upload_response = client.post(
            "/api/v1/documents",
            data={"source_id": "manual-source", "title": "设备维护规程"},
            files={
                "file": (
                    "maintenance.txt",
                    (
                        "设备维护规程\n\n"
                        "在执行设备维护前，操作人员必须断开设备电源，"
                        "并确认指示灯已经熄灭。\n\n"
                        "完成维护并检查防护装置后，方可重新接通电源。"
                    ).encode(),
                    "text/plain",
                )
            },
        )
        assert upload_response.status_code == 202
        accepted = upload_response.json()

        # 中文：单次 Worker 轮询必须完成真实切块和 FAISS/BM25 不可变索引发布。
        # English: One worker poll must complete real chunking and immutable FAISS/BM25
        # publication.
        assert container.worker.run_once() is True

        detail_response = client.get(f"/api/v1/documents/{accepted['document_id']}")
        assert detail_response.status_code == 200
        assert detail_response.json()["status"] == "ready"

        chat_response = client.post(
            "/api/v1/chat",
            json={"query": "设备维护前必须断开什么？"},
        )

    assert chat_response.status_code == 200
    answer = chat_response.json()
    assert answer["status"] == "answered"
    assert answer["answer"] == "设备维护前必须断开电源[C1]。"
    assert len(answer["citations"]) == 1
    assert answer["citations"][0]["document_id"] == accepted["document_id"]
