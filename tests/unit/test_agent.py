"""中文：本模块负责实现“测试智能体”相关功能。

English: Verify bounded agent retries, evidence refusal, answer generation, and citation checks.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from enterprise_rag.agent.answer_generator import AnswerGenerator
from enterprise_rag.agent.citation_verifier import CitationVerifier
from enterprise_rag.agent.evidence_grader import EvidenceGrader
from enterprise_rag.agent.intent_router import IntentRouter
from enterprise_rag.agent.orchestrator import AgentOrchestrator
from enterprise_rag.agent.query_rewriter import QueryRewriter
from enterprise_rag.agent.state import AgentState
from enterprise_rag.domain.models import Chunk, RetrievalScope
from enterprise_rag.domain.protocols.models import ModelResponse, ModelUsage
from enterprise_rag.domain.results import AnswerResult, RefusalResult
from enterprise_rag.retrieval.models import (
    EvidenceBundle,
    EvidenceItem,
    RoutingResult,
    TopKDecision,
)


class FakeLLM:
    """中文：该类用于表示或实现“模拟大语言模型（FakeLLM）”的职责。

    English: Return queued deterministic model text and zero-cost usage.
    """

    def __init__(self, responses: list[str]) -> None:
        """中文：初始化当前实例，并保存后续操作所需的依赖、配置或状态。

        English: Store response text in call order.
        """

        # 中文：变量 `_responses` 用于保存“`responses`”相关数据；
        # 其精确定义与约束见下方英文说明。
        # English: Mutable queue simulates provider calls.
        self._responses = responses

    @property
    def fingerprint(self) -> str:
        """中文：该函数或方法负责“指纹”相关处理。

        English: Return a stable test provider fingerprint.
        """

        return "fake:test"

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        metadata: object = None,
    ) -> ModelResponse:
        """中文：该函数或方法负责“完成一次模型调用”相关处理。

        English: Return and remove the next queued response.
        """

        del system_prompt, user_prompt, metadata
        return ModelResponse(
            text=self._responses.pop(0),
            usage=ModelUsage(input_tokens=10, output_tokens=5),
            model="fake",
        )


def _scope() -> RetrievalScope:
    """中文：该内部函数负责“范围”相关处理。

    English: Create one pinned authorized retrieval scope.
    """

    return RetrievalScope(
        tenant_id="tenant-a",
        source_ids=frozenset({"source-a"}),
        index_version_id="index-a",
    )


def _evidence(text: str) -> EvidenceBundle:
    """中文：该内部函数负责“证据”相关处理。

    English: Create one citable evidence bundle.
    """

    # 中文：变量 `chunk` 用于保存“文本块”相关数据；其精确定义与约束见下方英文说明。
    # English: Immutable chunk contains the policy claim.
    chunk = Chunk(
        id="chunk-a",
        tenant_id="tenant-a",
        source_id="source-a",
        document_id="document-a",
        document_version_id="version-a",
        ordinal=0,
        text=text,
        token_count=10,
        page_start=2,
        page_end=2,
        heading_path=("Leave Policy",),
        previous_chunk_id=None,
        next_chunk_id=None,
        boundary_reason="document_end",
        chunker_version="test-v1",
        content_hash="hash",
    )
    # 中文：变量 `item` 用于保存“`item`”相关数据；其精确定义与约束见下方英文说明。
    # English: Evidence item receives the label referenced by the fake answer.
    item = EvidenceItem("C1", chunk, 1.0)
    return EvidenceBundle(
        index_version_id="index-a",
        items=(item,),
        context_text=f"[C1]\n<UNTRUSTED_DOCUMENT>{text}</UNTRUSTED_DOCUMENT>",
        token_count=10,
        routing=RoutingResult(("source-a",), "single_source", "test"),
        top_k=TopKDecision(1, "test"),
    )


def _state(query: str) -> AgentState:
    """中文：该内部函数负责“状态”相关处理。

    English: Create a fresh state with a future deadline.
    """

    return AgentState(
        trace_id="trace-a",
        original_query=query,
        current_query=query,
        retrieval_scope=_scope(),
        deadline=datetime.now(UTC) + timedelta(seconds=30),
    )


def test_agent_returns_verified_cited_answer() -> None:
    """中文：该测试用于验证“智能体返回已验证的带引用的答案”相关行为。

    English: Ensure sufficient evidence reaches generation and deterministic citation
    verification.
    """

    # 中文：变量 `provider` 用于保存“提供方”相关数据；其精确定义与约束见下方英文说明。
    # English: Fake provider is called only for answer generation in this successful path.
    provider = FakeLLM(["Annual leave requires manager approval [C1]."])
    # 中文：变量 `retrieve` 用于保存“执行一次检索”相关数据；其精确定义与约束见下方英文说明。
    # English: Retriever always returns policy evidence.
    retrieve = lambda query, round_number: _evidence(  # noqa: E731
        "Annual leave requires manager approval."
    )
    orchestrator = AgentOrchestrator(
        IntentRouter(),
        retrieve,
        EvidenceGrader(minimum_coverage=0.3),
        QueryRewriter(provider),
        AnswerGenerator(provider),
        CitationVerifier(minimum_claim_overlap=0.3),
        max_retrieval_retries=2,
        max_model_calls=8,
        max_total_tokens=1000,
    )

    result = orchestrator.run(_state("Does annual leave require manager approval?"))

    assert isinstance(result, AnswerResult)
    assert result.citations[0].chunk_id == "chunk-a"
    assert result.retrieval_rounds == 1


def test_agent_stops_after_initial_plus_two_retrievals() -> None:
    """中文：该测试用于验证“智能体停止之后初始加上两次`retrievals`”相关行为。

    English: Ensure evidence gaps cannot create an unbounded retrieval loop.
    """

    # 中文：变量 `provider` 用于保存“提供方”相关数据；其精确定义与约束见下方英文说明。
    # English: Two queued rewrites cover the maximum two retries.
    provider = FakeLLM(["first rewritten query", "second rewritten query"])
    # 中文：变量 `calls` 用于保存“`calls`”相关数据；其精确定义与约束见下方英文说明。
    # English: Every round returns irrelevant evidence so the grader remains insufficient.
    calls: list[tuple[str, int]] = []

    def retrieve(query: str, round_number: int) -> EvidenceBundle:
        """中文：该函数或方法负责“执行一次检索”相关处理。

        English: Record each bounded retrieval and return irrelevant evidence.
        """

        calls.append((query, round_number))
        return _evidence("Unrelated cafeteria opening hours.")

    orchestrator = AgentOrchestrator(
        IntentRouter(),
        retrieve,
        EvidenceGrader(minimum_coverage=0.8),
        QueryRewriter(provider),
        AnswerGenerator(provider),
        CitationVerifier(),
        max_retrieval_retries=2,
        max_model_calls=8,
        max_total_tokens=1000,
    )

    result = orchestrator.run(_state("What is the quantum encryption policy?"))

    assert isinstance(result, RefusalResult)
    assert len(calls) == 3
    assert [round_number for _, round_number in calls] == [1, 2, 3]
